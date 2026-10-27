"""후속 규정 알림 — 근거 원문을 바꾸는 후속 공식 문서를 기록하고, 영향받는 원고·보고서·카드뉴스를 찾아 재검토를 요구한다.

원칙:
- 알림은 산출물의 내용·검증 상태를 자동으로 바꾸지 않는다(연구원이 확인·수정한다).
- 영향 범위는 근거 각주/카드 근거의 원문 URL에 기존 문서 번호가 들어 있는지로 판단한다(휴리스틱이므로 연구원이 최종 판단).
- 확인(ack)은 '수정 반영' 또는 '변경 없음(영향 없음)'을 사유와 함께 남기는 기록이며 검증 완료가 아니다.
"""

import json
import uuid
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.card_news import CardNews, CardNewsEvidence
from app.models.followup import FollowupAck, FollowupNotice
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.report import Report, ReportItem

FR_API = "https://www.federalregister.gov/api/v1"
ENTITY_TYPES = ("manuscript", "report", "card_news")


def _matches(notice: FollowupNotice, url: str | None) -> bool:
    if not url:
        return False
    return notice.original_doc_number in url or (bool(notice.original_url) and url.rstrip("/") == notice.original_url.rstrip("/"))


def notice_out(n: FollowupNotice) -> dict:
    try:
        changes = json.loads(n.changes_json) if n.changes_json else []
    except ValueError:
        changes = []
    return {
        "id": str(n.id), "title": n.title, "original_doc_number": n.original_doc_number, "original_url": n.original_url,
        "followup_doc_number": n.followup_doc_number, "followup_url": n.followup_url, "followup_org": n.followup_org,
        "followup_published_at": n.followup_published_at.isoformat() if n.followup_published_at else None,
        "followup_effective_on": n.followup_effective_on, "change_summary": n.change_summary, "changes": changes,
        "is_pilot": n.is_pilot, "created_at": n.created_at.isoformat(),
    }


def affected_manuscript_ids(db: Session, notice: FollowupNotice) -> set[uuid.UUID]:
    ids = set()
    for fn in db.scalars(select(ManuscriptFootnote)).all():
        if _matches(notice, fn.source_url):
            ids.add(fn.manuscript_id)
    return ids


def affected_entities(db: Session, notice: FollowupNotice) -> dict[str, set[uuid.UUID]]:
    ms_ids = affected_manuscript_ids(db, notice)
    report_ids = set(db.scalars(select(ReportItem.report_id).where(ReportItem.manuscript_id.in_(ms_ids))).all()) if ms_ids else set()
    cn_ids = set()
    for ev in db.scalars(select(CardNewsEvidence)).all():
        if _matches(notice, ev.source_url) or (ev.source_manuscript_id in ms_ids):
            cn_ids.add(ev.card_news_id)
    if report_ids:  # 보고서에서 생성한 카드뉴스는 원본 보고서가 영향받으면 함께 표시한다
        for cn in db.scalars(select(CardNews).where(CardNews.source_report_id.in_(report_ids))).all():
            cn_ids.add(cn.id)
    return {"manuscript": ms_ids, "report": report_ids, "card_news": cn_ids}


def acked(db: Session, notice_id: uuid.UUID) -> dict[tuple[str, uuid.UUID], FollowupAck]:
    return {(a.entity_type, a.entity_id): a for a in db.scalars(select(FollowupAck).where(FollowupAck.notice_id == notice_id)).all()}


def open_notices_for(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[dict]:
    """해당 산출물에 대해 아직 확인(ack)되지 않은 후속 규정 알림."""
    out = []
    for n in db.scalars(select(FollowupNotice).order_by(FollowupNotice.created_at)).all():
        if entity_id not in affected_entities(db, n)[entity_type]:
            continue
        if (entity_type, entity_id) in acked(db, n.id):
            continue
        out.append(notice_out(n))
    from app.services import ai_insertion_service  # AI 삽입 문장의 근거 원문이 바뀐 경우도 같은 '재검토 필요' 통로로 전달한다

    out.extend(ai_insertion_service.open_changes_for(db, entity_type, entity_id))
    return out


def impact_summary(db: Session, notice: FollowupNotice) -> dict:
    """알림 1건의 영향 산출물과 확인 상태."""
    aff = affected_entities(db, notice)
    acks = acked(db, notice.id)
    result = {}
    for etype, ids in aff.items():
        rows = []
        for eid in ids:
            title = None
            if etype == "manuscript":
                obj = db.get(Manuscript, eid)
            elif etype == "report":
                obj = db.get(Report, eid)
            else:
                obj = db.get(CardNews, eid)
            title = obj.title if obj else None
            a = acks.get((etype, eid))
            rows.append({"id": str(eid), "title": title, "acked": a is not None,
                         "resolution": a.resolution if a else None, "note": a.note if a else None,
                         "acked_at": a.created_at.isoformat() if a else None})
        result[etype] = sorted(rows, key=lambda r: (r["acked"], r["title"] or ""))
    return result


def fetch_federal_register(doc_number: str, timeout: float = 20.0) -> dict:
    """연방관보 공식 API에서 문서 메타데이터를 가져온다(네트워크). 후속 규정의 공식 확인용."""
    fields = ["title", "publication_date", "effective_on", "abstract", "html_url", "document_number", "docket_ids", "type", "dates"]
    r = httpx.get(f"{FR_API}/documents/{doc_number}.json", params=[("fields[]", f) for f in fields], timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def detect_candidates(db: Session, timeout: float = 20.0) -> list[dict]:
    """연방관보 근거 각주마다 같은 기관의 더 새로운 문서 중 같은 표준·규정 번호를 언급하는 후보를 찾는다.
    후보는 자동 등록하지 않는다(연구원이 확인 후 알림으로 등록)."""
    seen: dict[str, dict] = {}
    for fn in db.scalars(select(ManuscriptFootnote)).all():
        if "federalregister.gov/documents/" not in (fn.source_url or ""):
            continue
        parts = fn.source_url.rstrip("/").split("/")
        doc = next((p for p in parts if len(p) > 6 and p[4:5] == "-" and p[:4].isdigit()), None)
        if doc and doc not in seen:
            seen[doc] = {"doc": doc, "url": fn.source_url}
    existing = {n.followup_doc_number for n in db.scalars(select(FollowupNotice)).all()}
    candidates = []
    for doc, info in seen.items():
        try:
            meta = fetch_federal_register(doc, timeout)
            term = meta["title"].split(";")[1].strip()[:80] if ";" in meta["title"] else meta["title"][:80]
            r = httpx.get(f"{FR_API}/documents.json", timeout=timeout, params=[
                ("conditions[term]", f'"{term}"'), ("order", "newest"), ("per_page", "20"),
                ("fields[]", "document_number"), ("fields[]", "publication_date"), ("fields[]", "title"),
                ("fields[]", "type"), ("fields[]", "effective_on"), ("fields[]", "html_url")])
            r.raise_for_status()
        except (httpx.HTTPError, KeyError, ValueError):
            continue
        for d in r.json().get("results", []):
            if d["document_number"] != doc and d["publication_date"] > meta["publication_date"] and d["document_number"] not in existing \
                    and d.get("type") == "Rule":
                candidates.append({"original_doc_number": doc, "original_url": info["url"], "followup_doc_number": d["document_number"],
                                   "followup_url": d["html_url"], "title": d["title"], "published_at": d["publication_date"],
                                   "effective_on": d.get("effective_on")})
    return candidates


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if "T" in s else datetime.fromisoformat(s + "T00:00:00+00:00")
