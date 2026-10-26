"""카드뉴스 생성·편집·근거·버전·검토·출력(PPTX/PNG) 서비스.

원칙
- 카드뉴스의 사실·수치·일정은 원문 근거와 연결하고, 검증은 연구원이 명시적으로 해야 한다(원고 각주가 검증되었어도
  카드에서는 별도로 확인). 검증 당시의 텍스트 해시를 저장해 이후 내용이 바뀌면 '재검토 필요'가 된다.
- 보고서에서 가져온 문장은 원문 문장 스냅샷(source_sentence)을 함께 저장해, 원고가 바뀌면 '원본 변경·재검토 필요'로 표시한다.
  이미 편집한 카드 내용은 원고가 바뀌어도 자동으로 덮어쓰지 않는다.
- 출력은 출력 시점의 카드 내용·템플릿 버전을 고정한 스냅샷으로 만들고, PPTX/PNG 모두 같은 장면 데이터를 쓴다.
"""

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.card_news import (
    CardNews, CardNewsCard, CardNewsElement, CardNewsEvidence, CardNewsExport, CardNewsReview, CardNewsTemplate,
    CardNewsVersion,
)
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.report import Report, ReportItem
from app.models.source_document import SourceDocument
from app.services import card_news_pptx, card_news_render, card_news_scene, followup_service, report_pdf
from app.services.card_news_schema import (
    DEFAULT_HEIGHT_CM, DEFAULT_WIDTH_CM, FILL_ORDER, STAGE_KINDS, STAGE_SLOTS, TEMPLATES, default_card_kinds, element_specs, template_config,
)

BLOCKING_CODES = {
    "empty_required", "missing_source", "text_overflow", "out_of_bounds", "text_overlap", "unverified_claim",
    "claim_without_evidence", "evidence_stale", "source_stale", "chart_incomplete", "followup_pending",
}
CONFLICT_MESSAGE = "다른 사용자가 먼저 수정했습니다. 최신 내용을 다시 불러온 뒤 수정하세요."
DATE_RE = re.compile(r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.?")


class ExportInProgressError(Exception):
    pass


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


def text_hash(text: str | None, data: dict | None = None) -> str:
    raw = _norm(text) + ("|" + json.dumps(data, sort_keys=True, ensure_ascii=False) if data else "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def export_dir() -> Path:
    path = Path(settings.export_dir) / "card_news"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- 템플릿 ----
def ensure_templates(db: Session) -> dict[str, CardNewsTemplate]:
    out: dict[str, CardNewsTemplate] = {}
    for key, meta in TEMPLATES.items():
        row = db.scalars(select(CardNewsTemplate).where(
            CardNewsTemplate.template_key == key, CardNewsTemplate.is_active.is_(True)
        ).order_by(CardNewsTemplate.version.desc())).first()
        if row is None:
            row = CardNewsTemplate(template_key=key, name=meta["name"], version=1, config_json="{}", is_active=True)
            db.add(row)
            db.flush()
        out[key] = row
    return out


def create_template_version(db: Session, row: CardNewsTemplate, patch: dict, user_id: uuid.UUID) -> CardNewsTemplate:
    current = json.loads(row.config_json or "{}")
    current.update(patch)
    row.is_active = False
    new = CardNewsTemplate(template_key=row.template_key, name=row.name, version=row.version + 1,
                           config_json=json.dumps(current, ensure_ascii=False), is_active=True, created_by_user_id=user_id)
    db.add(new)
    db.flush()
    return new


def config_for(db: Session, cn: CardNews) -> tuple[dict, CardNewsTemplate]:
    row = db.get(CardNewsTemplate, cn.template_id) if cn.template_id else ensure_templates(db)[cn.template_key]
    cfg = template_config(cn.template_key, json.loads(row.config_json or "{}"))
    cfg["width_cm"], cfg["height_cm"] = cn.width_cm, cn.height_cm
    return cfg, row


# ---------------------------------------------------------------- 카드·요소 생성 ----
def _new_card(db: Session, cn: CardNews, kind: str, position: int) -> CardNewsCard:
    card = CardNewsCard(card_news_id=cn.id, kind=kind, position=position)
    db.add(card)
    db.flush()
    for spec in element_specs(cn.template_key, kind):
        text = ""
        if spec.type == "choice":
            text = "other"
        if spec.key == "badge":
            text = "주간 AI·ICT 동향"
        db.add(CardNewsElement(card_id=card.id, key=spec.key, element_type=spec.type, text=text))
    db.flush()
    return card


def _cards(db: Session, cn: CardNews) -> list[CardNewsCard]:
    return list(db.scalars(select(CardNewsCard).where(CardNewsCard.card_news_id == cn.id).order_by(CardNewsCard.position)).all())


def _elements(db: Session, card: CardNewsCard) -> dict[str, CardNewsElement]:
    return {e.key: e for e in db.scalars(select(CardNewsElement).where(CardNewsElement.card_id == card.id)).all()}


def _footnotes_overlapping(db: Session, manuscript_id: uuid.UUID, sentence: str) -> list[ManuscriptFootnote]:
    sent = _norm(sentence)
    out = []
    for fn in db.scalars(select(ManuscriptFootnote).where(ManuscriptFootnote.manuscript_id == manuscript_id)).all():
        anchor = _norm(fn.anchor_text)
        if anchor and sent and (anchor in sent or sent in anchor):
            out.append(fn)
    return out


def add_evidence_from_footnote(db: Session, cn: CardNews, card: CardNewsCard, key: str, fn: ManuscriptFootnote, user_id: uuid.UUID) -> CardNewsEvidence:
    ms = db.get(Manuscript, fn.manuscript_id)
    ev = CardNewsEvidence(
        card_news_id=cn.id, card_id=card.id, element_key=key, source_manuscript_id=fn.manuscript_id, source_footnote_id=fn.id,
        source_document_id=fn.source_document_id, source_url=fn.source_url, source_org=fn.source_org, excerpt=fn.excerpt,
        original_footnote_status=fn.verification_status.value, source_lock_version=ms.lock_version if ms else None,
        verification_status="not_verified", created_by_user_id=user_id,
    )
    db.add(ev)
    return ev


def _doc_title(db: Session, fn: ManuscriptFootnote) -> str | None:
    if fn.source_document_id:
        doc = db.get(SourceDocument, fn.source_document_id)
        return doc.title if doc else None
    return None


def create_card_news(
    db: Session, *, user_id: uuid.UUID, title: str, template_key: str, source_type: str = "manual",
    source_report_id: uuid.UUID | None = None, selections: list[dict] | None = None, body_count: int = 3,
    width_cm: float | None = None, height_cm: float | None = None, is_pilot: bool = False, is_synthetic: bool = False,
) -> CardNews:
    if template_key not in TEMPLATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "알 수 없는 템플릿입니다")
    templates = ensure_templates(db)
    selections = selections or []
    if selections:
        body_count = max(body_count, -(-len(selections) // max(len(FILL_ORDER[template_key]), 1)))
    cn = CardNews(
        title=title, template_key=template_key, template_id=templates[template_key].id, source_type=source_type,
        source_report_id=source_report_id, width_cm=width_cm or DEFAULT_WIDTH_CM, height_cm=height_cm or DEFAULT_HEIGHT_CM,
        is_pilot=is_pilot, is_synthetic=is_synthetic, created_by_user_id=user_id, status="draft",
    )
    db.add(cn)
    db.flush()
    cards = [_new_card(db, cn, kind, pos) for pos, kind in enumerate(default_card_kinds(body_count))]
    cover = _elements(db, cards[0])
    cover["title"].text = title
    body_cards = [c for c in cards if c.kind == "body"]

    versions: dict[str, int] = {}
    slots = FILL_ORDER[template_key]
    orgs: list[str] = []
    for n, sel in enumerate(selections):
        card = body_cards[n // len(slots)]
        els = _elements(db, card)
        key = slots[n % len(slots)]
        ms = db.get(Manuscript, uuid.UUID(str(sel["manuscript_id"])))
        if ms is None:
            continue
        versions[str(ms.id)] = ms.lock_version
        sentence = sel["sentence"].strip()
        el = els[key]
        el.text = sentence
        el.source_manuscript_id = ms.id
        el.source_sentence = sentence
        if n % len(slots) == 0 and not els["heading"].text:
            els["heading"].text = ms.title[:30]
        if template_key == "B":
            m = DATE_RE.search(sentence)
            idx = key.split("_")[1]
            if m:  # 문장에 실제로 들어 있는 날짜만 옮긴다(날짜를 만들어 넣지 않음)
                els[f"stage_{idx}_date"].text = m.group(0)
        fns = _footnotes_overlapping(db, ms.id, sentence)
        evidence_key = key
        for fn in fns:
            add_evidence_from_footnote(db, cn, card, evidence_key, fn, user_id)
            label = " ".join(x for x in (fn.source_org, _doc_title(db, fn)) if x)
            if label and not els["source"].text:
                els["source"].text = label[:70]
            if fn.source_org:
                orgs.append(fn.source_org)
    if orgs:
        cover["source"].text = orgs[0][:70]
    cn.source_versions_json = json.dumps(versions, ensure_ascii=False) if versions else None
    db.flush()
    snapshot(db, cn, user_id, note="생성", milestone=True)
    return cn


# ---------------------------------------------------------------- 직렬화·상태 계산 ----
def _source_stale(db: Session, el: CardNewsElement, cache: dict) -> bool:
    if not el.source_manuscript_id or not el.source_sentence:
        return False
    ms = cache.get(el.source_manuscript_id)
    if ms is None:
        ms = db.get(Manuscript, el.source_manuscript_id)
        cache[el.source_manuscript_id] = ms
    if ms is None:
        return True
    return _norm(el.source_sentence) not in _norm(ms.body)


def _load_json(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return None


def _evidence_state(el: CardNewsElement, evs: list[CardNewsEvidence]) -> str:
    """none / not_verified / verified / stale(검증 후 내용 수정)."""
    if not evs:
        return "none"
    current = text_hash(el.text, _load_json(el.data_json))
    if any(e.verification_status == "verified" and e.verified_text_hash == current for e in evs):
        return "verified"
    if any(e.verification_status == "verified" for e in evs):
        return "stale"
    return "not_verified"


def ev_out(e: CardNewsEvidence, el: CardNewsElement | None = None) -> dict:
    state = e.verification_status
    if state == "verified" and el is not None and e.verified_text_hash != text_hash(el.text, _load_json(el.data_json)):
        state = "stale"
    return {
        "id": str(e.id), "card_id": str(e.card_id), "element_key": e.element_key, "source_url": e.source_url,
        "source_org": e.source_org, "excerpt": e.excerpt, "original_footnote_status": e.original_footnote_status,
        "source_manuscript_id": str(e.source_manuscript_id) if e.source_manuscript_id else None,
        "source_footnote_id": str(e.source_footnote_id) if e.source_footnote_id else None,
        "verification_status": state, "verified_by_user_id": str(e.verified_by_user_id) if e.verified_by_user_id else None,
        "verified_at": e.verified_at.isoformat() if e.verified_at else None,
    }


DOC_NO_RE = re.compile(r"/(\d{4}-\d{4,6})(?:/|$)")
STATE_LABEL = {"verified": "연구원 검증됨", "not_verified": "근거 미검증", "stale": "검증 후 수정됨·재검증 필요", "none": "근거 없음"}


def _short_org(org: str | None, url: str) -> str:
    if org:
        m = re.search(r"\(([A-Za-z0-9 .&-]{2,20})\)", org)
        if m:
            return m.group(1)
        return org[:8]
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0][:16]


def source_entries(db: Session, evs: list[CardNewsEvidence], els: dict[str, CardNewsElement]) -> list[dict]:
    """카드의 근거를 출처 표기용 항목으로 정리한다(같은 URL은 한 번만). 발표일·문서번호는 원문 식별에 쓰며, 알 수 없으면 비운다."""
    out: dict[str, dict] = {}
    for e in evs:
        entry = out.get(e.source_url)
        el = els.get(e.element_key)
        state = ev_out(e, el)["verification_status"]
        if entry is None:
            m = DOC_NO_RE.search(e.source_url)
            published = None
            doc_title = None
            if e.source_document_id:
                doc = db.get(SourceDocument, e.source_document_id)
                if doc is not None:
                    published = doc.published_at.date().isoformat() if doc.published_at else None
                    doc_title = doc.title
            if published is None and e.source_footnote_id:  # 수집 문서가 없는 근거는 원고 각주의 발표일을 쓴다
                fn = db.get(ManuscriptFootnote, e.source_footnote_id)
                if fn is not None and fn.published_at:
                    published = fn.published_at.date().isoformat()
            doc_no = m.group(1) if m else None
            label = f"{_short_org(e.source_org, e.source_url)} {doc_no}" if doc_no else _short_org(e.source_org, e.source_url)
            out[e.source_url] = {"label": label.strip(), "url": e.source_url, "org": e.source_org, "doc_no": doc_no,
                                 "doc_title": doc_title, "published": published, "states": {state}, "elements": {e.element_key}}
        else:
            entry["states"].add(state)
            entry["elements"].add(e.element_key)
    result = []
    for entry in out.values():
        entry["state"] = "verified" if entry["states"] == {"verified"} else ("stale" if "stale" in entry["states"] else "not_verified")
        entry["states"], entry["elements"] = sorted(entry["states"]), sorted(entry["elements"])
        result.append(entry)
    return result


def card_inputs(db: Session, cn: CardNews, *, for_export: bool) -> tuple[list[dict], dict]:
    """장면 빌더에 넘길 카드 입력과 공통 ctx를 만든다."""
    cards = _cards(db, cn)
    evidences = list(db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == cn.id)).all())
    labels = {}
    out = []
    for idx, card in enumerate(cards, start=1):
        els = _elements(db, card)
        for spec in element_specs(cn.template_key, card.kind):
            labels[spec.key] = spec.label
        elem_dicts = {}
        for key, el in els.items():
            d = card_news_scene.element_dict(el)
            elem_dicts[key] = d
        chart_verified = False
        if "chart" in els:
            chart_verified = _evidence_state(els["chart"], [e for e in evidences if e.card_id == card.id and e.element_key == "chart"]) == "verified"
        sources = source_entries(db, [e for e in evidences if e.card_id == card.id], els)
        out.append({"id": str(card.id), "kind": card.kind, "bg_color": card.bg_color, "elements": elem_dicts, "index": idx,
                    "total": len(cards), "chart_verified": chart_verified, "sources": sources,
                    "links": [{"label": s["label"], "url": s["url"]} for s in sources] if for_export else []})
    ctx = {"for_export": for_export, "labels": labels, "is_pilot": cn.is_pilot, "is_synthetic": cn.is_synthetic,
           "iitp_confirmed": cn.iitp_confirmed}
    return out, ctx


def build_scenes(db: Session, cn: CardNews, *, for_export: bool) -> list[dict]:
    cfg, _ = config_for(db, cn)
    inputs, ctx = card_inputs(db, cn, for_export=for_export)
    scenes = []
    for card in inputs:
        c = dict(ctx, chart_verified=card["chart_verified"])
        scene = card_news_scene.build_card_scene(cn.width_cm, cn.height_cm, cfg, cn.template_key, card, c)
        scene["card_id"] = card["id"]
        scene["sources"] = card["sources"]
        scenes.append(scene)
    return scenes


def run_preflight(db: Session, cn: CardNews) -> list[dict]:
    cfg, _ = config_for(db, cn)
    cards = _cards(db, cn)
    evidences = list(db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == cn.id)).all())
    cache: dict = {}
    issues: list[dict] = []
    title_sizes = set()

    def add(level, code, msg, card_idx=None, key=None):
        issues.append({"level": level, "code": code, "message": (f"[{card_idx}번 카드] " if card_idx else "") + msg,
                       "card_index": card_idx, "element_key": key})

    scenes = build_scenes(db, cn, for_export=True)
    for idx, card in enumerate(cards, start=1):
        els = _elements(db, card)
        specs = element_specs(cn.template_key, card.kind)
        for spec in specs:
            el = els.get(spec.key)
            if el is None or el.hidden:
                continue
            text = (el.text or "").strip()
            if spec.type == "chart":
                data = _load_json(el.data_json)
                if data:
                    problems = card_news_scene.validate_chart(data)
                    if problems:
                        add("error", "chart_incomplete", "그래프 데이터가 불완전합니다: " + ", ".join(problems), idx, spec.key)
                    elif not data.get("synthetic") and _evidence_state(el, [e for e in evidences if e.card_id == card.id and e.element_key == "chart"]) != "verified":
                        add("warn", "unverified_claim", "그래프 수치의 근거가 검증되지 않아 그래프를 그리지 않고 메시지 중심 레이아웃으로 출력됩니다", idx, spec.key)
                continue
            if spec.type == "choice":
                continue
            if spec.required and not text:
                add("error", "empty_required", f"'{spec.label}'이(가) 비어 있습니다", idx, spec.key)
            if spec.key == "source" and spec.required and not text:
                add("error", "missing_source", "출처 표기가 없습니다", idx, spec.key)
            if text and len(text) > spec.max_chars:
                add("warn", "too_much_text", f"'{spec.label}' 글자 수 {len(text)}자가 권장 {spec.max_chars}자를 넘습니다 — 문장 축약·카드 분할을 검토하세요", idx, spec.key)
            if text and spec.evidence:
                evs = [e for e in evidences if e.card_id == card.id and e.element_key == spec.key]
                state = _evidence_state(el, evs)
                if state == "none":
                    add("warn", "claim_without_evidence", f"'{spec.label}'에 연결된 원문 근거가 없습니다", idx, spec.key)
                elif state == "not_verified":
                    add("warn", "unverified_claim", f"'{spec.label}'의 근거가 검증되지 않았습니다", idx, spec.key)
                elif state == "stale":
                    add("warn", "evidence_stale", f"'{spec.label}'이(가) 검증 이후 수정되어 재검증이 필요합니다", idx, spec.key)
            if _source_stale(db, el, cache):
                add("warn", "source_stale", f"'{spec.label}'의 원본 문장이 보고서·원고에서 바뀌었습니다 — 원본 변경·재검토 필요", idx, spec.key)
        if card.kind == "body" and "heading" in els:
            sz = _load_json(els["heading"].style_json) or {}
            title_sizes.add(sz.get("size"))
        if card.kind == "body" and not (els.get("heading") and (els["heading"].text or "").strip()):
            add("error", "missing_title", "카드 제목이 없습니다", idx, "heading")
    for n in followup_service.open_notices_for(db, "card_news", cn.id):
        add("error", "followup_pending", f"후속 규정이 발견되어 재검토가 필요합니다(연구원 확인 전): {n['title'][:60]}")
    if len(title_sizes) > 1:
        add("warn", "inconsistent_style", "카드마다 제목 글자 크기가 다릅니다 — 디자인 일관성을 확인하세요")
    for idx, scene in enumerate(scenes, start=1):
        for it in card_news_scene.check_scene(scene, cfg):
            add(it["level"], it["code"], it["message"], idx, it.get("key"))
    if not cn.iitp_confirmed:
        add("info", "iitp_unconfirmed", "IITP 공식 확인 전입니다 — 내부 승인과 별개이며 출력본에 '내부 검토용'으로 표시됩니다")
    if cn.is_pilot:
        add("info", "pilot_content", "시범 카드뉴스입니다 — 실제 발간물이 아닌 개발용 출력 테스트입니다")
    if cn.is_synthetic:
        add("info", "synthetic_content", "합성 테스트 데이터가 포함되어 있습니다 — 실제 ICT 동향이 아닙니다")
    return issues


def blocking(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i["code"] in BLOCKING_CODES]


def detail(db: Session, cn: CardNews) -> dict:
    cards = _cards(db, cn)
    evidences = list(db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == cn.id)).all())
    cache: dict = {}
    card_out = []
    source_changed = False
    try:
        base = json.loads(cn.source_versions_json or "{}")
    except ValueError:
        base = {}
    for mid, ver in base.items():
        ms = db.get(Manuscript, uuid.UUID(mid))
        if ms is None or ms.lock_version != ver:
            source_changed = True
    stale_any = False
    for card in cards:
        els = _elements(db, card)
        el_out = []
        for spec in element_specs(cn.template_key, card.kind):
            el = els.get(spec.key)
            if el is None:
                continue
            evs = [e for e in evidences if e.card_id == card.id and e.element_key == spec.key]
            stale = _source_stale(db, el, cache)
            stale_any = stale_any or stale
            d = spec.as_dict()
            d.update({
                "text": el.text or "", "data": _load_json(el.data_json), "style": _load_json(el.style_json) or {},
                "box": _load_json(el.box_json) or {}, "hidden": el.hidden, "source_sentence": el.source_sentence,
                "source_manuscript_id": str(el.source_manuscript_id) if el.source_manuscript_id else None,
                "source_stale": stale, "evidence_state": _evidence_state(el, evs) if spec.evidence else "n/a",
                "evidence": [ev_out(e, el) for e in evs],
            })
            el_out.append(d)
        card_out.append({"id": str(card.id), "position": card.position, "kind": card.kind, "bg_color": card.bg_color, "elements": el_out})
    issues = run_preflight(db, cn)
    return {
        "id": str(cn.id), "title": cn.title, "template_key": cn.template_key, "template_name": TEMPLATES[cn.template_key]["name"],
        "width_cm": cn.width_cm, "height_cm": cn.height_cm, "status": cn.status, "lock_version": cn.lock_version,
        "source_type": cn.source_type, "source_report_id": str(cn.source_report_id) if cn.source_report_id else None,
        "source_changed": source_changed, "needs_review": stale_any, "iitp_confirmed": cn.iitp_confirmed, "iitp_note": cn.iitp_note,
        "is_pilot": cn.is_pilot, "is_synthetic": cn.is_synthetic, "approve_exception_reason": cn.approve_exception_reason,
        "reviewer_user_id": str(cn.reviewer_user_id) if cn.reviewer_user_id else None,
        "created_by_user_id": str(cn.created_by_user_id), "updated_at": cn.updated_at.isoformat(),
        "cards": card_out, "preflight": issues, "blocking": blocking(issues),
        "followups_open": followup_service.open_notices_for(db, "card_news", cn.id),
        "size_note": "작업용 기본 규격 7×15.62cm — IITP 공식 발간 규격으로 확인된 값이 아닙니다",
    }


# ---------------------------------------------------------------- 편집 공통 ----
def assert_lock(cn: CardNews, lock_version: int) -> None:
    if cn.lock_version != lock_version:
        raise HTTPException(status.HTTP_409_CONFLICT, CONFLICT_MESSAGE)


def assert_editable(cn: CardNews) -> None:
    if cn.status == "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "내부 확정된 카드뉴스입니다 — 승인권자가 '확정 해제'하거나 새 수정 버전을 만들어야 수정할 수 있습니다")


def bump(cn: CardNews) -> None:
    cn.lock_version += 1
    cn.updated_at = datetime.now(timezone.utc)


def snapshot_dict(db: Session, cn: CardNews) -> dict:
    cards = []
    for card in _cards(db, cn):
        els = _elements(db, card)
        cards.append({
            "id": str(card.id), "kind": card.kind, "position": card.position, "bg_color": card.bg_color,
            "elements": [{"id": str(e.id), "key": e.key, "type": e.element_type, "text": e.text, "data": e.data_json, "style": e.style_json,
                          "box": e.box_json, "hidden": e.hidden,
                          "source_manuscript_id": str(e.source_manuscript_id) if e.source_manuscript_id else None,
                          "source_sentence": e.source_sentence} for e in els.values()],
        })
    evidences = [{
        "id": str(e.id), "card_id": str(e.card_id), "element_key": e.element_key, "source_url": e.source_url, "source_org": e.source_org,
        "excerpt": e.excerpt, "source_manuscript_id": str(e.source_manuscript_id) if e.source_manuscript_id else None,
        "source_footnote_id": str(e.source_footnote_id) if e.source_footnote_id else None,
        "source_document_id": str(e.source_document_id) if e.source_document_id else None,
        "original_footnote_status": e.original_footnote_status, "source_lock_version": e.source_lock_version,
        "verification_status": e.verification_status, "verified_text_hash": e.verified_text_hash,
        "verified_by_user_id": str(e.verified_by_user_id) if e.verified_by_user_id else None,
        "verified_at": e.verified_at.isoformat() if e.verified_at else None, "created_by_user_id": str(e.created_by_user_id),
    } for e in db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == cn.id)).all()]
    return {"title": cn.title, "template_key": cn.template_key, "width_cm": cn.width_cm, "height_cm": cn.height_cm,
            "cards": cards, "evidence": evidences}


def snapshot(db: Session, cn: CardNews, user_id: uuid.UUID, *, note: str | None = None, milestone: bool = False) -> CardNewsVersion | None:
    """주요 버전은 항상, 자동 스냅샷은 마지막 스냅샷이 60초 이상 지났을 때만 남긴다(자동저장마다 쌓지 않음)."""
    last = db.scalars(select(CardNewsVersion).where(CardNewsVersion.card_news_id == cn.id).order_by(CardNewsVersion.version_no.desc())).first()
    if not milestone and last is not None:
        created = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created < timedelta(seconds=60):
            return None
    ver = CardNewsVersion(
        card_news_id=cn.id, version_no=(last.version_no + 1) if last else 1, is_milestone=milestone, change_note=note,
        snapshot_json=json.dumps(snapshot_dict(db, cn), ensure_ascii=False), edited_by_user_id=user_id,
    )
    db.add(ver)
    db.flush()
    return ver


def restore_version(db: Session, cn: CardNews, ver: CardNewsVersion, user_id: uuid.UUID) -> None:
    data = json.loads(ver.snapshot_json)
    # 현재 상태를 먼저 주요 버전으로 남긴 뒤(되돌릴 수 있게) 복원한다
    snapshot(db, cn, user_id, note=f"복원 전 상태(v{ver.version_no}로 복원)", milestone=True)
    for ev in db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == cn.id)).all():
        db.delete(ev)
    old_cards = _cards(db, cn)
    for card in old_cards:
        for el in db.scalars(select(CardNewsElement).where(CardNewsElement.card_id == card.id)).all():
            db.delete(el)
    db.flush()  # 자식(근거·요소)을 먼저 지운 뒤 카드를 지운다(PostgreSQL 외래키 순서)
    for review in db.scalars(select(CardNewsReview).where(CardNewsReview.card_news_id == cn.id)).all():
        review.card_id = None  # 복원으로 사라질 카드를 가리키는 검토 의견은 카드 연결만 해제한다
    for card in old_cards:
        db.delete(card)
    db.flush()
    cn.title = data["title"]
    for c in data["cards"]:
        card = CardNewsCard(id=uuid.UUID(c["id"]), card_news_id=cn.id, kind=c["kind"], position=c["position"], bg_color=c["bg_color"])
        db.add(card)
        db.flush()
        for e in c["elements"]:
            db.add(CardNewsElement(
                id=uuid.UUID(e["id"]), card_id=card.id, key=e["key"], element_type=e["type"], text=e["text"], data_json=e["data"],
                style_json=e["style"], box_json=e["box"], hidden=e["hidden"],
                source_manuscript_id=uuid.UUID(e["source_manuscript_id"]) if e["source_manuscript_id"] else None,
                source_sentence=e["source_sentence"]))
    db.flush()
    for e in data["evidence"]:
        db.add(CardNewsEvidence(
            id=uuid.UUID(e["id"]), card_news_id=cn.id, card_id=uuid.UUID(e["card_id"]), element_key=e["element_key"],
            source_url=e["source_url"], source_org=e["source_org"], excerpt=e["excerpt"],
            source_manuscript_id=uuid.UUID(e["source_manuscript_id"]) if e["source_manuscript_id"] else None,
            source_footnote_id=uuid.UUID(e["source_footnote_id"]) if e["source_footnote_id"] else None,
            source_document_id=uuid.UUID(e["source_document_id"]) if e["source_document_id"] else None,
            original_footnote_status=e["original_footnote_status"], source_lock_version=e["source_lock_version"],
            verification_status=e["verification_status"], verified_text_hash=e["verified_text_hash"],
            verified_by_user_id=uuid.UUID(e["verified_by_user_id"]) if e["verified_by_user_id"] else None,
            verified_at=datetime.fromisoformat(e["verified_at"]) if e["verified_at"] else None,
            created_by_user_id=uuid.UUID(e["created_by_user_id"])))
    db.flush()


def change_template(db: Session, cn: CardNews, new_key: str) -> None:
    """템플릿을 바꾼다. 같은 키의 요소는 값을 유지하고, 핵심 내용 슬롯은 순서대로 옮긴다(내용을 만들어 넣지 않음)."""
    if new_key not in TEMPLATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "알 수 없는 템플릿입니다")
    old_key = cn.template_key
    if old_key == new_key:
        return
    templates = ensure_templates(db)
    old_slots, new_slots = FILL_ORDER[old_key], FILL_ORDER[new_key]
    for card in _cards(db, cn):
        old_els = _elements(db, card)
        # 삭제 전에 값을 복사해 둔다(삭제된 ORM 객체에 접근하지 않기 위해)
        carried = {k: {"type": e.element_type, "text": e.text, "style": e.style_json, "data": e.data_json,
                       "sm": e.source_manuscript_id, "ss": e.source_sentence} for k, e in old_els.items()}
        moves = {}  # 핵심 내용 슬롯은 순서대로 새 템플릿 슬롯으로 이동
        for pos, okey in enumerate(old_slots):
            if pos < len(new_slots) and okey in carried and (carried[okey]["text"] or "").strip():
                moves[new_slots[pos]] = carried[okey]
        for el in list(old_els.values()):
            db.delete(el)
        db.flush()
        created: dict[str, CardNewsElement] = {}
        for spec in element_specs(new_key, card.kind):
            prior = carried.get(spec.key)
            src = moves.get(spec.key) or prior
            if spec.type == "choice":
                text = prior["text"] if prior and prior["type"] == "choice" else "other"
            elif spec.type == "text":
                text = (src["text"] if src and src["type"] == "text" else "") or ""
            else:
                text = ""
            if spec.key == "badge" and not text:
                text = "주간 AI·ICT 동향"
            new_el = CardNewsElement(card_id=card.id, key=spec.key, element_type=spec.type, text=text)
            if src and spec.type == "text" and src["type"] == "text":
                new_el.source_manuscript_id, new_el.source_sentence = src["sm"], src["ss"]
            if prior and prior["type"] == spec.type and spec.key not in moves:
                new_el.style_json, new_el.data_json = prior["style"], prior["data"]
            db.add(new_el)
            created[spec.key] = new_el
        if new_key == "B":  # 옮겨 온 문장에 실제로 들어 있는 날짜만 날짜 칸에 채운다(날짜를 만들어 넣지 않음)
            for i in range(1, STAGE_SLOTS + 1):
                t, d = created.get(f"stage_{i}_text"), created.get(f"stage_{i}_date")
                if t is not None and d is not None and t.text and not d.text:
                    m = DATE_RE.search(t.text)
                    if m:
                        d.text = m.group(0)
    # 근거 연결은 요소 키 기준이므로, 옮겨지지 않은 키의 근거는 정리하고 옮겨진 슬롯의 근거는 키를 따라간다
    evidences = list(db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == cn.id)).all())
    keymap = {old_slots[p]: new_slots[p] for p in range(min(len(old_slots), len(new_slots)))}
    valid_keys = {s.key for kind in ("cover", "body", "closing") for s in element_specs(new_key, kind)}
    for e in evidences:
        nk = keymap.get(e.element_key, e.element_key)
        if nk in valid_keys:
            e.element_key = nk
        else:
            db.delete(e)
    cn.template_key = new_key
    cn.template_id = templates[new_key].id
    db.flush()


# ---------------------------------------------------------------- 출력 ----
def generate_export(db: Session, cn: CardNews, *, file_format: str, user_id: uuid.UUID, short_px: int = 1000) -> CardNewsExport:
    if file_format not in ("pptx", "png"):
        raise ValueError("지원하지 않는 형식입니다")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    for r in db.scalars(select(CardNewsExport).where(
        CardNewsExport.card_news_id == cn.id, CardNewsExport.file_format == file_format, CardNewsExport.status == "running"
    )).all():
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        if created > recent:
            raise ExportInProgressError("같은 카드뉴스의 같은 형식 출력이 이미 진행 중입니다")
        r.status, r.error_message = "failed", "시간 초과로 중단된 이전 요청"

    cfg, tpl = config_for(db, cn)
    snap = snapshot_dict(db, cn)  # 이 시점의 내용을 고정한다
    scenes = build_scenes(db, cn, for_export=True)
    issues = run_preflight(db, cn)
    export = CardNewsExport(
        card_news_id=cn.id, file_format=file_format, status="running", content_version=cn.lock_version, template_id=tpl.id,
        template_version=tpl.version, source_versions_json=cn.source_versions_json, snapshot_json=json.dumps(snap, ensure_ascii=False),
        card_count=len(scenes), approval_state=("approved" if cn.status == "approved" else cn.status), created_by_user_id=user_id,
    )
    db.add(export)
    db.commit()
    try:
        pptx_bytes = card_news_pptx.build_pptx(scenes, cn.title, cfg["font"])
        safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", cn.title)[:36].strip("_") or "cardnews"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tag = "확정" if cn.status == "approved" else "초안"
        extra_issues: list[dict] = []
        validation: dict = {"rendered": False}
        if file_format == "pptx":
            payload = pptx_bytes
            file_name = f"{safe}_{stamp}_{tag}.pptx"
            if report_pdf.find_soffice() is not None:  # 가능하면 실제 렌더링으로 검증한다
                _pngs, pdf, sizes = card_news_render.render_pngs(pptx_bytes, 400)
                extra_issues = card_news_render.check_rendered(pdf, scenes)
                validation = {"rendered": True}
            else:
                extra_issues.append({"level": "info", "code": "not_rendered", "message": "LibreOffice가 없어 렌더링 점검을 하지 못했습니다", "key": None})
        else:
            pngs, pdf, sizes = card_news_render.render_pngs(pptx_bytes, short_px)
            extra_issues = card_news_render.check_rendered(pdf, scenes)
            folder = export_dir() / f"{export.id}_png"
            folder.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for n, png in enumerate(pngs, start=1):
                    (folder / f"card-{n:02d}.png").write_bytes(png)
                    zf.writestr(f"{safe}_card-{n:02d}.png", png)
                zf.writestr(f"{safe}_출처목록.txt", sources_text(cn, scenes, sizes), )
            payload = buf.getvalue()
            file_name = f"{safe}_{stamp}_{tag}_png.zip"
            export.png_width_px, export.png_height_px = sizes[0]
            validation = {"rendered": True, "png_sizes": sizes, "aspect_ratio_pptx": round(cn.width_cm / cn.height_cm, 4),
                          "aspect_ratio_png": round(sizes[0][0] / sizes[0][1], 4)}
        path = export_dir() / f"{export.id}.{'pptx' if file_format == 'pptx' else 'zip'}"
        path.write_bytes(payload)
        export.file_name, export.file_path = file_name, str(path)
        export.file_sha256, export.file_size = hashlib.sha256(payload).hexdigest(), len(payload)
        validation["issues"] = issues + extra_issues
        export.validation_json = json.dumps(validation, ensure_ascii=False)
        export.status = "success"
        export.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        export = db.get(CardNewsExport, export.id)
        export.status = "failed"
        export.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        export.finished_at = datetime.now(timezone.utc)
        db.commit()
    db.refresh(export)
    return export


def sources_text(cn: CardNews, scenes: list[dict], sizes: list[tuple[int, int]]) -> str:
    """PNG는 클릭할 수 없으므로 카드별 출처(원문 URL·발표일·문서번호·검증 상태)를 텍스트로 함께 제공한다."""
    lines = [f"{cn.title}", "카드뉴스 출처 목록 — 내부 검토용(IITP 공식 확인 전)이며 검증 상태는 내부 검증 기록 기준입니다."]
    if cn.is_synthetic:
        lines.append("※ 합성 테스트 데이터가 포함되어 있습니다 — 실제 정책·통계가 아닙니다.")
    if cn.is_pilot:
        lines.append("※ 시범 카드뉴스입니다 — 실제 발간물이 아닙니다.")
    for n, scene in enumerate(scenes, start=1):
        w, h = sizes[n - 1] if n - 1 < len(sizes) else (0, 0)
        lines += ["", f"[카드 {n}/{len(scenes)}] {w}×{h}px"]
        srcs = scene.get("sources") or []
        if not srcs:
            lines.append("  연결된 원문 근거 없음")
        for src in srcs:
            lines.append("  - " + " · ".join(x for x in (src["label"], src.get("doc_title"), f"발표일 {src['published']}" if src.get("published") else None,
                                                          STATE_LABEL.get(src["state"], src["state"])) if x))
            lines.append(f"    {src['url']}")
    return "\n".join(lines) + "\n"


def export_out(e: CardNewsExport) -> dict:
    return {
        "id": str(e.id), "card_news_id": str(e.card_news_id), "file_format": e.file_format, "status": e.status,
        "error_message": e.error_message, "content_version": e.content_version, "template_version": e.template_version,
        "file_name": e.file_name, "file_sha256": e.file_sha256, "file_size": e.file_size, "card_count": e.card_count,
        "png_width_px": e.png_width_px, "png_height_px": e.png_height_px, "approval_state": e.approval_state,
        "source_versions_json": e.source_versions_json, "validation_json": e.validation_json,
        "created_by_user_id": str(e.created_by_user_id), "created_at": e.created_at.isoformat(),
        "finished_at": e.finished_at.isoformat() if e.finished_at else None,
    }


# ---------------------------------------------------------------- 보고서 문장 후보 ----
def source_sentences(db: Session, report: Report) -> list[dict]:
    """보고서(일반·특집·요약본)에서 카드에 쓸 수 있는 원고 문장 후보. 각주 연결 여부와 원고 각주 검증 상태를 함께 보여준다."""
    items = db.scalars(select(ReportItem).where(ReportItem.report_id == report.id).order_by(ReportItem.position)).all()
    out: list[dict] = []
    seen: set = set()
    for item in items:
        ms = db.get(Manuscript, item.manuscript_id) if item.manuscript_id else None
        if ms is None:
            continue
        if item.summary_text is not None:  # 요약본: 연구원이 선택한 원문 문장을 후보로 쓴다
            candidates = [(item.source_sentence or item.summary_text, item.summary_text)]
        else:
            candidates = [(ln.strip(), ln.strip()) for ln in (ms.body or "").splitlines() if len(ln.strip()) >= 8]
        for source_sentence, shown in candidates:
            key = (ms.id, _norm(source_sentence))
            if key in seen:
                continue
            seen.add(key)
            fns = _footnotes_overlapping(db, ms.id, source_sentence)
            out.append({
                "manuscript_id": str(ms.id), "manuscript_title": ms.title, "sentence": source_sentence, "shown": shown,
                "footnotes": [{"id": str(f.id), "source_org": f.source_org, "source_url": f.source_url,
                               "status": f.verification_status.value} for f in fns],
            })
    return out
