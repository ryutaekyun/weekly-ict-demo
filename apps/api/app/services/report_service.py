"""보고서(일반호·특집호·요약본) 구성 → 스냅샷 고정 → 발간 점검 → DOCX/PDF 출력본 생성.

핵심 원칙
- 출력은 항상 '스냅샷'(그 시점의 원고 본문·각주·템플릿 버전을 JSON으로 고정한 입력)으로만 만든다.
  → 출력 중 다른 연구원이 원고를 고쳐도 한 파일 안에 서로 다른 버전이 섞이지 않는다.
- 근거 검증 상태는 건드리지 않는다. 각주가 있다는 이유로 '검증 완료'가 되지 않는다.
- 내부 검토용 초안은 언제든 출력 가능하지만, '출력용 확정'은 필수 점검을 통과하거나 승인권자가
  예외 사유를 남긴 경우에만 가능하다. IITP 공식 확인은 별도 플래그(iitp_confirmed)다.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.edition import Edition
from app.models.enums import EvidenceMatchStatus, ManuscriptStatus
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.manuscript_version import ManuscriptVersion
from app.models.report import Report, ReportExport, ReportItem, ReportTemplate
from app.models.user import User
from app.models.source_document import SourceDocument
from app.services import followup_service, report_docx, report_pdf

GENERAL_PARTS = [
    ("key_issue", "주요 이슈", True),
    ("country_trend", "주요국 동향", True),
    ("field_brief", "ICT 9대 분야 주요 단신", False),
    ("schedule", "주요 일정", False),
]
SUMMARY_PARTS = [
    ("key_issue", "주요 이슈 요약", True),
    ("country_trend", "주요국 동향 요약", True),
    ("key_message", "핵심 메시지", False),
]
PART_LABELS = {k: label for k, label, _ in GENERAL_PARTS + SUMMARY_PARTS}
PART_PAGE_LIMIT = {"key_issue": 10, "country_trend": 10}  # 발간 지침: 파트당 10페이지 이내
REPORT_KIND_LABEL = {"general": "주간 AI·ICT 동향 (일반호)", "special": "주간 AI·ICT 동향 (특집호)", "summary": "주간 AI·ICT 동향 요약본"}

# 출력용 확정을 막는 점검 코드(승인권자의 예외 사유가 있으면 통과 가능)
BLOCKING_CODES = {"required_part_missing", "empty_manuscript", "unverified_footnotes", "manuscript_not_approved", "summary_stale", "followup_pending"}


class ExportInProgressError(Exception):
    pass


def export_dir() -> Path:
    path = Path(settings.export_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _norm(text: str) -> str:
    return " ".join((text or "").split())


# ---------------------------------------------------------------- 템플릿 ----
def get_active_template(db: Session, name: str = "임시 표준 템플릿") -> ReportTemplate:
    template = db.scalars(
        select(ReportTemplate).where(ReportTemplate.name == name, ReportTemplate.is_active.is_(True))
        .order_by(ReportTemplate.version.desc())
    ).first()
    if template is None:
        template = ReportTemplate(
            name=name, version=1, is_active=True, is_provisional=True,
            config_json=json.dumps(report_docx.DEFAULT_TEMPLATE_CONFIG, ensure_ascii=False),
        )
        db.add(template)
        db.flush()
    return template


def create_template_version(db: Session, template: ReportTemplate, config_patch: dict, user_id: uuid.UUID) -> ReportTemplate:
    """서식 수정은 항상 새 버전 행을 만든다 — 과거 출력본이 쓴 서식은 그대로 보존."""
    current = json.loads(template.config_json)
    merged = report_docx.merge_template_config({**current, **config_patch})
    template.is_active = False
    new = ReportTemplate(
        name=template.name, version=template.version + 1, is_active=True, is_provisional=template.is_provisional,
        config_json=json.dumps(merged, ensure_ascii=False), created_by_user_id=user_id,
    )
    db.add(new)
    db.flush()
    return new


# ---------------------------------------------------------------- 스냅샷 ----
def _footnote_dict(db: Session, fn: ManuscriptFootnote) -> dict:
    doc_title = None
    if fn.source_document_id is not None:
        doc = db.get(SourceDocument, fn.source_document_id)
        doc_title = doc.title if doc is not None else None
    return {
        "mark_id": fn.mark_id, "anchor_text": fn.anchor_text, "doc_title": doc_title, "source_org": fn.source_org,
        "source_url": fn.source_url, "excerpt": fn.excerpt, "location_label": fn.location_label,
        "published_at": fn.published_at.isoformat() if fn.published_at else None,
        "accessed_at": fn.accessed_at.isoformat() if fn.accessed_at else None,
        "verification_status": fn.verification_status.value,
    }


def _manuscript_block(db: Session, manuscript: Manuscript) -> dict:
    footnotes = db.scalars(select(ManuscriptFootnote).where(ManuscriptFootnote.manuscript_id == manuscript.id)).all()
    latest = db.scalars(
        select(ManuscriptVersion).where(ManuscriptVersion.manuscript_id == manuscript.id)
        .order_by(ManuscriptVersion.version_no.desc())
    ).first()
    body_json = json.loads(manuscript.body_json) if manuscript.body_json else {"type": "doc", "content": []}
    note = None
    if manuscript.status != ManuscriptStatus.APPROVED:
        note = "※ 원고 상태: 내부 승인 전(초안·검토 중)"
    return {
        "id": str(manuscript.id), "title": manuscript.title, "title_en": manuscript.title_en,
        "body_json": body_json, "body_text": manuscript.body or "", "lock_version": manuscript.lock_version,
        "version_no": latest.version_no if latest else 0, "status": manuscript.status.value,
        "is_pilot": manuscript.is_pilot, "iitp_selection_status": manuscript.iitp_selection_status.value,
        "footnotes": {fn.mark_id: _footnote_dict(db, fn) for fn in footnotes}, "status_note": note,
    }


DATE_RE = re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*[.일]?")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|퍼센트|kg|㎏|건|명|개|억|조|만|원|달러|GW|MW|TWh|GB|TB|nm|배|년|개월|일)")


def extract_facts(text: str | None) -> set[str]:
    """문장에서 핵심 사실(날짜·단위가 붙은 수치)을 뽑는다. 정확한 의미 비교가 아니라 변경 여부를 알리는 보조 지표다."""
    text = text or ""
    facts = {f"{int(y):04d}-{int(m):02d}-{int(d):02d}" for y, m, d in DATE_RE.findall(text)}
    rest = DATE_RE.sub(" ", text)
    for m in NUM_RE.findall(rest):
        facts.add(re.sub(r"[\s,]", "", m))
    return facts


def best_new_sentence(old_sentence: str, body: str) -> tuple[str | None, float]:
    """원고의 현재 본문에서 옛 요약 원문 문장과 가장 비슷한 문장을 찾는다(없으면 None)."""
    import difflib

    old_n = _norm(old_sentence)
    candidates = [c.strip() for c in re.split(r"\n+", body or "") if c.strip()]
    best, score = None, 0.0
    for c in candidates:
        r = difflib.SequenceMatcher(a=old_n, b=_norm(c)).ratio()
        if r > score:
            best, score = c, r
    return (best, round(score, 2)) if score >= 0.35 else (None, round(score, 2))


def fact_diff(old_sentence: str, body: str) -> dict:
    new_sentence, ratio = best_new_sentence(old_sentence, body)
    old_f, new_f = extract_facts(old_sentence), extract_facts(new_sentence)
    return {"old_sentence": old_sentence, "new_sentence": new_sentence, "similarity": ratio,
            "removed": sorted(old_f - new_f), "added": sorted(new_f - old_f)}


def _summary_item_block(db: Session, item: ReportItem) -> dict:
    ms = db.get(Manuscript, item.manuscript_id) if item.manuscript_id else None
    footnotes: dict[str, dict] = {}
    footnote_ids: list[str] = []
    stale = False
    fact_changes = None
    past_facts: list[str] = []
    review = None
    if ms is not None:
        source = _norm(item.source_sentence or "")
        source_changed = bool(source) and source not in _norm(ms.body or "")
        if source_changed:
            fact_changes = fact_diff(item.source_sentence or "", ms.body or "")
            # 요약문에 남아 있는, 현재 원고의 대응 문장에는 없는 과거 사실
            current = extract_facts(fact_changes["new_sentence"]) if fact_changes["new_sentence"] else set()
            past_facts = sorted(f for f in extract_facts(item.summary_text) if f in fact_changes["removed"] and f not in current)
        reviewed = item.fact_review_status is not None and item.fact_reviewed_lock_version == ms.lock_version
        if item.fact_review_status:
            reviewer = db.get(User, item.fact_reviewed_by_user_id) if item.fact_reviewed_by_user_id else None
            review = {"resolution": item.fact_review_status, "note": item.fact_review_note, "reviewer": reviewer.display_name if reviewer else None,
                      "reviewed_at": item.fact_reviewed_at.isoformat() if item.fact_reviewed_at else None, "current": reviewed}
        # 재검토가 끝나려면 연구원 기록이 있어야 하고(원고가 그 뒤 또 바뀌면 다시 필요), 과거 사실이 요약문에 남아 있으면 안 된다
        stale = (source_changed and not reviewed) or bool(past_facts)
        for fn in db.scalars(select(ManuscriptFootnote).where(ManuscriptFootnote.manuscript_id == ms.id)).all():
            anchor = _norm(fn.anchor_text)
            if anchor and source and (anchor in source or source in anchor):
                footnotes[fn.mark_id] = _footnote_dict(db, fn)
                footnote_ids.append(fn.mark_id)
    return {
        "item_id": str(item.id), "text": item.summary_text or "", "source_sentence": item.source_sentence,
        "source_manuscript_id": str(item.manuscript_id) if item.manuscript_id else None,
        "source_manuscript_title": ms.title if ms else None, "needs_review": stale,
        "fact_changes": fact_changes, "past_facts": past_facts, "fact_review": review,
        "footnotes": footnotes, "footnote_ids": footnote_ids,
    }


def build_snapshot(db: Session, report: Report) -> dict:
    template = db.get(ReportTemplate, report.template_id) if report.template_id else get_active_template(db)
    items = db.scalars(select(ReportItem).where(ReportItem.report_id == report.id).order_by(ReportItem.position)).all()
    edition = db.get(Edition, report.edition_id) if report.edition_id else None

    raw: list[dict] = []  # 번호 매기기 전의 파트 목록: {key, label, required, manuscripts, summary_items}
    if report.report_type == "general":
        for key, label, required in GENERAL_PARTS:
            group = [i for i in items if i.part_key == key and i.manuscript_id]
            raw.append({"key": key, "label": label, "required": required,
                        "manuscripts": [_manuscript_block(db, db.get(Manuscript, i.manuscript_id)) for i in group]})
        known = {k for k, _, _ in GENERAL_PARTS}
        for i in [i for i in items if i.manuscript_id and i.part_key not in known]:
            raw.append({"key": i.part_key or "free", "label": i.heading or "추가 원고", "required": False,
                        "manuscripts": [_manuscript_block(db, db.get(Manuscript, i.manuscript_id))]})
    elif report.report_type == "special":
        for n, item in enumerate([i for i in items if i.manuscript_id], start=1):
            block = _manuscript_block(db, db.get(Manuscript, item.manuscript_id))
            heading = item.heading or block["title"]
            block["hide_title"] = _norm(heading) == _norm(block["title"])
            raw.append({"key": "free", "label": heading, "required": True, "manuscripts": [block], "numeric": True})
    else:  # summary
        for key, label, required in SUMMARY_PARTS:
            group = [i for i in items if i.part_key == key and i.summary_text is not None]
            raw.append({"key": key, "label": label, "required": required, "manuscripts": [],
                        "summary_items": [_summary_item_block(db, i) for i in group]})

    # 출력용 확정본에서는 비어 있는 '선택 파트'를 출력에서 뺀다(확정본에 '미완성' 문구가 남는 모순 방지).
    # 필수 파트가 비어 있는데 확정된 경우는 승인권자의 예외 승인이므로 파트를 유지하고 상태 표기에 '예외 승인'을 남긴다.
    if report.status == "final":
        raw = [r for r in raw if r["manuscripts"] or r.get("summary_items") or r["required"]]
    parts: list[dict] = []
    for idx, r in enumerate(raw):
        numeral = f"{idx + 1}." if r.get("numeric") else f"{report_docx.ROMAN[min(idx, 9)]}."
        parts.append({"key": r["key"], "heading": f"{numeral} {r['label']}", "required": r["required"],
                      "manuscripts": r["manuscripts"], "summary_items": r.get("summary_items", [])})

    all_ms = [m for p in parts for m in p.get("manuscripts", [])]
    is_pilot = any(m["is_pilot"] for m in all_ms)
    if report.report_type == "summary":
        for p in parts:
            for si in p.get("summary_items", []):
                src = si.get("source_manuscript_id")
                if src:
                    ms = db.get(Manuscript, uuid.UUID(src))
                    is_pilot = is_pilot or bool(ms and ms.is_pilot)
    return {
        "report": {
            "id": str(report.id), "type": report.report_type, "kind_label": REPORT_KIND_LABEL[report.report_type],
            "title": report.title, "title_en": report.title_en,
            "edition_label": edition.edition_label if edition else None,
            "publish_date": (report.publish_date or (datetime.combine(edition.target_date, datetime.min.time()) if edition else None)).isoformat()
            if (report.publish_date or edition) else None,
            "iitp_confirmed": report.iitp_confirmed, "is_pilot": is_pilot, "status": report.status,
            "layout": report.layout, "exception": bool(report.finalize_exception_reason),
            "followups_open": [n["title"] for n in followup_service.open_notices_for(db, "report", report.id)],
        },
        "template": {
            "id": str(template.id), "name": template.name, "version": template.version,
            "is_provisional": template.is_provisional, "config": json.loads(template.config_json),
        },
        "parts": parts,
    }


# ---------------------------------------------------------------- 발간 점검 ----
_NUMERIC_CLAIM = re.compile(r"(\d{4}\.\s?\d{1,2}\.\s?\d{1,2}|\d{1,2}\s?%|\d[\d,]*\s?(?:억|만|건|kg|kW|달러|원|명))")


def _paragraph_texts_with_footnote(body_json: dict) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []

    def walk(node: dict) -> None:
        if node.get("type") in ("paragraph", "listItem") and node.get("type") == "paragraph":
            text = "".join(n.get("text", "") for n in node.get("content", []) if n.get("type") == "text")
            has_fn = any(
                m.get("type") == "footnoteMark" for n in node.get("content", []) for m in (n.get("marks") or [])
            )
            out.append((text, has_fn))
        for child in node.get("content", []) or []:
            walk(child)

    walk(body_json)
    return out


def run_preflight(snapshot: dict) -> list[dict]:
    issues: list[dict] = []
    rtype = snapshot["report"]["type"]

    def add(level: str, code: str, message: str, part: str | None = None) -> None:
        issues.append({"level": level, "code": code, "message": message, "part": part})

    for title in snapshot["report"].get("followups_open", []):
        add("error", "followup_pending", f"후속 규정 또는 근거 원문 변경이 발견되어 재검토가 필요합니다(연구원 확인 전): {title[:60]}")
    defs = GENERAL_PARTS if rtype == "general" else SUMMARY_PARTS if rtype == "summary" else []
    required = {k: (label, req) for k, label, req in defs}
    for part in snapshot["parts"]:
        filled = bool(part.get("manuscripts")) or bool(part.get("summary_items"))
        if part["key"] in required and not filled:
            label, req = required[part["key"]]
            add("error" if req else "warn", "required_part_missing" if req else "optional_part_empty",
                f"'{label}' 파트에 원고가 없습니다" + (" — 필수 목차 누락" if req else " — 내용이 없으면 임의로 채우지 않고 비워 둡니다"), part["key"])
    if rtype == "special" and not snapshot["parts"]:
        add("error", "required_part_missing", "특집호에 배치된 원고가 없습니다")

    unverified = 0
    total_fn = 0
    for part in snapshot["parts"]:
        for ms in part.get("manuscripts", []):
            texts = _paragraph_texts_with_footnote(ms["body_json"])
            if not "".join(t for t, _ in texts).strip():
                add("error", "empty_manuscript", f"원고 '{ms['title']}'의 본문이 비어 있습니다", part["key"])
            for text, has_fn in texts:
                if _NUMERIC_CLAIM.search(text) and not has_fn:
                    add("warn", "unsupported_claim", f"근거 연결이 없는 수치·일정 문장 가능성: “{text[:50]}…” ({ms['title']})", part["key"])
            for fn in ms["footnotes"].values():
                total_fn += 1
                if fn["verification_status"] != EvidenceMatchStatus.MATCHED.value:
                    unverified += 1
                if not fn.get("source_url"):
                    add("error", "missing_source_url", f"출처 URL이 없는 각주가 있습니다 ({ms['title']})", part["key"])
            if ms["status"] != ManuscriptStatus.APPROVED.value:
                add("warn", "manuscript_not_approved", f"원고 '{ms['title']}'는 내부 승인 전 상태입니다", part["key"])
        for si in part.get("summary_items", []):
            if si["needs_review"]:
                add("warn", "summary_stale", "원고가 변경되어 재검토가 필요한 요약문이 있습니다: " + si["text"][:40], part["key"])
            for fn in si["footnotes"].values():
                if fn["verification_status"] != EvidenceMatchStatus.MATCHED.value:
                    unverified += 1
                total_fn += 1
    if unverified:
        add("warn", "unverified_footnotes", f"근거 미검증 각주 {unverified}건 / 전체 {total_fn}건 — 출력본에는 '[근거 미검증]'으로 표시됩니다")
    if not snapshot["report"]["iitp_confirmed"]:
        add("info", "iitp_unconfirmed", "IITP 공식 확인 전입니다 — 내부 승인과 별개이며 출력본에 '내부 검토용 초안'으로 표시됩니다")
    if snapshot["template"].get("is_provisional"):
        add("info", "provisional_template", "임시 표준 템플릿입니다 — IITP 공식 양식이 확보되면 템플릿 버전으로 교체하세요")
    if snapshot["report"]["is_pilot"]:
        add("info", "pilot_content", "시범 작성 원고가 포함되어 있습니다 — 실제 발간물이 아닌 개발용 출력 테스트입니다")
    return issues


def blocking_issues(issues: list[dict]) -> list[dict]:
    """출력용 확정을 막는 항목. 경고였던 '미승인 원고·미검증 각주·요약 재검토'도 확정 단계에서는 막는다."""
    return [i for i in issues if i["code"] in BLOCKING_CODES]


# ---------------------------------------------------------------- 출력 ----
def _count_pages_for_limits(parts_pages: list[dict], part_keys: list[str]) -> list[dict]:
    warnings = []
    for info, key in zip(parts_pages, part_keys):
        limit = PART_PAGE_LIMIT.get(key)
        if limit and info.get("pages") is not None and info["pages"] > limit:
            warnings.append({
                "level": "warn", "code": "page_limit_exceeded", "part": key,
                "message": f"'{info['heading']}' 파트가 실제 렌더링 기준 {info['pages']}페이지로 지침({limit}페이지 이내)을 초과했습니다",
            })
    return warnings


def generate_export(db: Session, report: Report, *, file_format: str, user_id: uuid.UUID, final: bool = False) -> ReportExport:
    if file_format not in ("docx", "pdf"):
        raise ValueError("지원하지 않는 형식입니다")

    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    running = db.scalars(select(ReportExport).where(
        ReportExport.report_id == report.id, ReportExport.file_format == file_format, ReportExport.status == "running",
    )).all()
    for r in running:
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        if created > recent:
            raise ExportInProgressError("같은 보고서의 같은 형식 출력이 이미 진행 중입니다")
        r.status = "failed"
        r.error_message = "시간 초과로 중단된 이전 요청"

    snapshot = build_snapshot(db, report)  # 이 시점에 입력을 고정한다
    template_id = uuid.UUID(snapshot["template"]["id"])
    issues = run_preflight(snapshot)
    versions = {m["id"]: {"lock_version": m["lock_version"], "version_no": m["version_no"]}
                for p in snapshot["parts"] for m in p.get("manuscripts", [])}
    export = ReportExport(
        report_id=report.id, file_format=file_format, status="running", template_id=template_id,
        template_version=snapshot["template"]["version"], snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        manuscript_versions_json=json.dumps(versions, ensure_ascii=False), is_final=final, created_by_user_id=user_id,
    )
    db.add(export)
    db.commit()

    try:
        compact = snapshot["report"].get("layout") == "compact"
        built = report_docx.build_docx(snapshot)
        analysis = None
        render_note = None
        toc_verified: bool | None = None
        docx_bytes = built.docx_bytes
        pdf_bytes = None
        if report_pdf.find_soffice() is not None:
            pdf_bytes = report_pdf.convert_docx_to_pdf(built.docx_bytes)
            analysis = report_pdf.analyze_pdf(pdf_bytes, built.headings, built.part_headings, has_toc=not compact)
            if not compact:
                # 목차 번호는 이 환경에서 실제로 렌더링한 쪽수로만 넣고, 번호를 넣은 뒤에도 쪽수가 바뀌면 다시 맞춘다(최대 3회)
                toc_verified = False
                for _attempt in range(3):
                    pages = analysis["heading_page_list"]
                    built = report_docx.build_docx(snapshot, pages)
                    docx_bytes = built.docx_bytes
                    pdf_bytes = report_pdf.convert_docx_to_pdf(docx_bytes)
                    analysis = report_pdf.analyze_pdf(pdf_bytes, built.headings, built.part_headings)
                    if analysis["heading_page_list"] == pages:
                        toc_verified = True
                        break
        elif file_format == "pdf":
            raise report_pdf.PdfUnavailableError("이 서버에는 LibreOffice가 없어 PDF를 생성할 수 없습니다")
        else:
            render_note = "LibreOffice가 없어 렌더링으로 페이지 수·목차 번호를 확인하지 못했습니다(목차는 Word에서 갱신하세요)"

        if file_format == "pdf":
            payload, ext = pdf_bytes, "pdf"
        else:
            payload, ext = docx_bytes, "docx"

        if analysis is not None:
            part_keys = [p["key"] for p in snapshot["parts"]]
            issues.extend(_count_pages_for_limits(analysis["part_pages"], part_keys))
            export.page_count = analysis["page_count"]
        if render_note:
            issues.append({"level": "info", "code": "not_rendered", "message": render_note, "part": None})
        if toc_verified is False:
            issues.append({"level": "warn", "code": "toc_unstable", "part": None,
                           "message": "목차 쪽수가 3회 재조판 후에도 수렴하지 않았습니다 — Word에서 목차 필드를 갱신해 확인하세요"})
        elif toc_verified:
            issues.append({"level": "info", "code": "toc_verified", "part": None,
                           "message": "목차 쪽수를 이 환경의 실제 렌더링 결과와 대조해 확인했습니다(다른 글꼴 환경에서는 쪽수가 달라질 수 있어 Word에서 목차 갱신을 권장)"})
        export.footnote_count = built.footnote_count
        export.table_count = built.table_count

        safe_title = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", report.title)[:40].strip("_") or "report"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        file_name = f"{safe_title}_{stamp}{'_확정' if final else '_초안'}.{ext}"
        path = export_dir() / f"{export.id}.{ext}"
        path.write_bytes(payload)
        export.file_name = file_name
        export.file_path = str(path)
        export.file_sha256 = hashlib.sha256(payload).hexdigest()
        export.file_size = len(payload)
        export.validation_json = json.dumps({
            "issues": issues,
            "part_pages": analysis["part_pages"] if analysis else None,
            "rendered": analysis is not None, "toc_verified": toc_verified,
        }, ensure_ascii=False)
        export.status = "success"
        export.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # 실패도 이력으로 남긴다
        db.rollback()
        export = db.get(ReportExport, export.id)
        export.status = "failed"
        export.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        export.finished_at = datetime.now(timezone.utc)
        db.commit()
    db.refresh(export)
    return export
