"""AI 문장의 원고 삽입·삽입 취소·원문 변경 재검토.

원칙
- 삽입은 연구원이 고른 문장만, 연구원이 지정한 위치(커서 문단 뒤·소제목 아래·원고 끝)에 넣고, 기존 문장·각주·승인은 건드리지 않는다.
- 삽입 기록(ai_insertions)에 AI 원문과 연구원 최종 문장, 삽입 시점의 원문 버전 해시·근거 발췌문을 따로 남긴다.
- 근거 원문이 바뀌면(해시 변경) 그 AI 문장은 '원문 변경·재검토 필요'로 표시하고 연구원이 4가지 중 하나를 선택해 해소한다.
  후속 규정이 등록됐다는 사실만으로 원고를 자동 수정하지 않는다. 과거 승인본·출력본은 삭제·덮어쓰지 않는다.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_analysis import AIAnalysis, AIClaim, AIInsertion
from app.models.document_full_text import DocumentFullText
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services import ai_evidence, manuscript_footnote_service, manuscript_service
from app.services.manuscript_service import ManuscriptConflictError

RESOLUTIONS = {"updated": "수정 반영 완료", "no_impact": "내용에 영향 없음", "needs_check": "추가 확인 필요", "removed": "문장 삭제·대체"}
AI_MARK = "aiInsert"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def current_hash(db: Session, document_id: uuid.UUID | None) -> str | None:
    """분석 입력 해시와 같은 규칙(content_hash 우선, 없으면 본문 sha256)으로 현재 원문 버전을 계산한다."""
    if document_id is None:
        return None
    ft = db.scalar(select(DocumentFullText).where(DocumentFullText.document_id == document_id))
    if ft is None or not ft.full_text:
        return None
    return ft.content_hash or hashlib.sha256(ft.full_text.encode()).hexdigest()


# ---------------------------------------------------------------- 삽입 ----
def _text_of(node: dict) -> str:
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_text_of(c) for c in node.get("content", []) or [])


def _plain(body: dict) -> str:
    return "\n".join(_text_of(n) for n in body.get("content", []))


def insertion_index(body: dict, position: dict | None) -> int:
    """top-level 노드 목록에서 새 문단이 들어갈 위치(삽입 후 인덱스)를 정한다."""
    nodes = body.setdefault("content", [])
    mode = (position or {}).get("mode", "end")
    if mode == "end":
        return len(nodes)
    if mode == "after_index":
        idx = (position or {}).get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= max(len(nodes), 1):
            if not nodes and idx in (0, None):
                return 0
            raise HTTPException(status_code=422, detail="삽입할 문단 위치가 올바르지 않습니다 — 원고가 바뀌었을 수 있으니 다시 선택하세요")
        return idx + 1
    if mode == "after_heading":
        want = ((position or {}).get("heading_text") or "").strip()
        for i, n in enumerate(nodes):
            if n.get("type") == "heading" and want and want in _text_of(n):
                return i + 1
        raise HTTPException(status_code=422, detail=f"소제목 '{want}'을(를) 원고에서 찾지 못했습니다")
    raise HTTPException(status_code=422, detail="삽입 위치 종류는 end·after_index·after_heading 중 하나여야 합니다")


def insert_claims(
    db: Session, analysis: AIAnalysis, manuscript: Manuscript, user: User, claims: list[AIClaim], *, lock_version: int,
    edited_texts: dict[str, str], position: dict | None,
) -> dict:
    try:
        body = json.loads(manuscript.body_json) if manuscript.body_json else {"type": "doc", "content": []}
    except json.JSONDecodeError:
        body = {"type": "doc", "content": []}
    nodes = body.setdefault("content", [])
    at = insertion_index(body, position)
    inputs = {d["id"]: d for d in json.loads(analysis.input_documents_json or "[]")}
    created: list[AIInsertion] = []
    footnote_count = 0
    for offset, c in enumerate(claims):
        final = (edited_texts.get(str(c.id)) or c.text).strip()
        ins_id = uuid.uuid4()
        marks: list[dict] = [{"type": AI_MARK, "attrs": {"insertionId": str(ins_id)}}]
        evs = [e for e in json.loads(c.evidence_json or "[]") if e.get("document_id") and e.get("quote")]
        fn_mark = None
        doc_id = None
        quote = None
        if evs:
            ev = evs[0]
            doc_id, quote = uuid.UUID(ev["document_id"]), ev["quote"]
        if c.claim_type == "fact" and evs and c.evidence_status != "not_found":
            doc = db.get(SourceDocument, doc_id)
            fn_mark = f"fn-{uuid.uuid4().hex[:12]}"
            manuscript_footnote_service.create_footnote(
                db, manuscript_id=manuscript.id, created_by_user_id=user.id, mark_id=fn_mark, anchor_text=final[:500],
                source_url=(doc.origin_url if doc and doc.origin_url else evs[0].get("url") or ""), source_document_id=doc_id,
                excerpt=quote[:1500], location_label=evs[0].get("location"), published_at=doc.published_at if doc else None,
            )
            marks.append({"type": "footnoteMark", "attrs": {"footnoteId": fn_mark}})
            footnote_count += 1
        nodes.insert(at + offset, {"type": "paragraph", "content": [{"type": "text", "text": final, "marks": marks}]})
        h = current_hash(db, doc_id) or (inputs.get(str(doc_id), {}).get("content_hash") if doc_id else None)
        ins = AIInsertion(
            id=ins_id, analysis_id=analysis.id, claim_id=c.id, manuscript_id=manuscript.id, footnote_mark_id=fn_mark, document_id=doc_id,
            inserted_by_user_id=user.id, ai_text=c.text, final_text=final, edited_by_researcher=final != c.text.strip(), quote_at_insert=quote,
            source_hash_at_insert=inputs.get(str(doc_id), {}).get("content_hash") if doc_id else None, baseline_hash=h,
            position_json=json.dumps({"mode": (position or {}).get("mode", "end"), "at": at + offset}, ensure_ascii=False),
        )
        if ins.source_hash_at_insert is None:
            ins.source_hash_at_insert = h
        db.add(ins)
        created.append(ins)
        c.inserted_manuscript_id = manuscript.id
    try:
        manuscript_service.update_manuscript_body(
            db, manuscript, title=None, title_en=None, body_json=json.dumps(body, ensure_ascii=False), body=_plain(body),
            lock_version=lock_version, actor_user_id=user.id, change_note=f"AI 제안 {len(claims)}문장 삽입(연구원 선택·미검증)", is_milestone=False,
        )
    except ManuscriptConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.flush()
    return {"insertion_ids": [str(i.id) for i in created], "footnotes_created": footnote_count, "inserted": len(created), "position_index": at}


def undo_insertion(db: Session, ins: AIInsertion, manuscript: Manuscript, user: User, lock_version: int) -> dict:
    """삽입 취소 — 연구원이 고치지 않은 AI 문단만 자동으로 지운다(고친 문단은 수동 삭제 안내)."""
    if ins.status != "active":
        raise HTTPException(status_code=409, detail="이미 취소·삭제 처리된 삽입입니다")
    body = json.loads(manuscript.body_json or '{"type":"doc","content":[]}')
    nodes = body.get("content", [])
    for i, n in enumerate(nodes):
        marks = [m for t in (n.get("content") or []) for m in (t.get("marks") or []) if m.get("type") == AI_MARK]
        if any(m.get("attrs", {}).get("insertionId") == str(ins.id) for m in marks):
            if _text_of(n).strip() != ins.final_text.strip():
                raise HTTPException(status_code=409, detail="연구원이 이 문단을 수정했으므로 자동 삭제하지 않습니다 — 편집기에서 직접 지우세요")
            del nodes[i]
            break
    else:
        raise HTTPException(status_code=404, detail="원고에서 이 AI 문장을 찾지 못했습니다(이미 삭제됐을 수 있음)")
    try:
        manuscript_service.update_manuscript_body(
            db, manuscript, title=None, title_en=None, body_json=json.dumps(body, ensure_ascii=False), body=_plain(body),
            lock_version=lock_version, actor_user_id=user.id, change_note="AI 삽입 문장 취소", is_milestone=False,
        )
    except ManuscriptConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if ins.footnote_mark_id:
        fn = db.scalar(select(ManuscriptFootnote).where(ManuscriptFootnote.manuscript_id == manuscript.id, ManuscriptFootnote.mark_id == ins.footnote_mark_id))
        if fn is not None and fn.verification_status.value == "not_verified":
            db.delete(fn)  # 검증되지 않은 AI 각주만 함께 제거한다(검증된 각주는 보존)
    ins.status = "undone"
    db.flush()
    return {"undone": True}


# ---------------------------------------------------------------- 원문 변경 감지·재검토 ----
def _facts(text: str) -> tuple[set[str], set[str]]:
    return ai_evidence.extract_dates(text), ai_evidence.extract_numbers(text)


def change_detail(db: Session, ins: AIInsertion) -> dict | None:
    """원문이 삽입 이후 바뀌었는지와 달라진 점을 계산한다(바뀌지 않았으면 None)."""
    if ins.status != "active" or ins.document_id is None:
        return None
    cur = current_hash(db, ins.document_id)
    if cur is None or cur == ins.baseline_hash:
        return None
    ft = db.scalar(select(DocumentFullText).where(DocumentFullText.document_id == ins.document_id))
    new_text = ft.full_text if ft else ""
    old_quote = ins.quote_at_insert or ""
    still, loc, _ = ai_evidence.locate_quote(new_text, old_quote) if old_quote else (False, None, "")
    from app.services.report_service import best_new_sentence  # 3-5의 문장 비교를 재사용한다

    new_sentence, sim = best_new_sentence(old_quote, new_text) if old_quote else (None, 0.0)
    od, on = _facts(old_quote)
    nd, nn = _facts(new_sentence or new_text if not still else old_quote)
    fd, fnum = _facts(ins.final_text)
    nd_all, nn_all = _facts(new_text)
    return {
        "current_hash": cur, "baseline_hash": ins.baseline_hash, "old_quote": old_quote[:600], "old_quote_still_in_source": still,
        "new_sentence": (new_sentence or "")[:600] if not still else None, "similarity": round(sim, 2),
        "removed_facts": sorted((od | on) - (nd | nn)) if not still else [],
        "added_facts": sorted((nd | nn) - (od | on)) if not still else [],
        # 문장에 쓴 날짜 중 새 원문에 더 이상 없는 값 — 후속 변경으로 틀려졌을 가능성이 큰 값
        "stale_in_sentence": sorted(d for d in fd if d not in nd_all) if not still else [],
        "last_review": {"resolution": ins.last_review_resolution, "note": ins.last_review_note, "reviewed_at": ins.last_reviewed_at.isoformat() if ins.last_reviewed_at else None} if ins.last_review_resolution else None,
    }


def insertion_out(db: Session, ins: AIInsertion) -> dict:
    detail = change_detail(db, ins)
    return {
        "id": str(ins.id), "analysis_id": str(ins.analysis_id), "claim_id": str(ins.claim_id), "footnote_mark_id": ins.footnote_mark_id,
        "document_id": str(ins.document_id) if ins.document_id else None, "ai_text": ins.ai_text, "final_text": ins.final_text,
        "edited_by_researcher": ins.edited_by_researcher, "quote_at_insert": ins.quote_at_insert, "source_hash_at_insert": ins.source_hash_at_insert,
        "status": ins.status, "inserted_at": ins.created_at.isoformat(), "needs_review": detail is not None, "change": detail,
        "history": json.loads(ins.review_history_json or "[]"),
    }


def list_for_manuscript(db: Session, manuscript_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(AIInsertion).where(AIInsertion.manuscript_id == manuscript_id).order_by(AIInsertion.created_at)).all()
    return [insertion_out(db, r) for r in rows]


def review_insertion(db: Session, ins: AIInsertion, manuscript: Manuscript, user: User, resolution: str, note: str) -> AIInsertion:
    if resolution not in RESOLUTIONS:
        raise HTTPException(status_code=422, detail="resolution은 updated·no_impact·needs_check·removed 중 하나여야 합니다")
    if len((note or "").strip()) < 3:
        raise HTTPException(status_code=422, detail="판단 사유를 3자 이상 입력해 주세요")
    if ins.status != "active":
        raise HTTPException(status_code=409, detail="이미 취소·삭제 처리된 삽입입니다")
    cur = current_hash(db, ins.document_id)
    detail = change_detail(db, ins)
    if resolution in ("updated", "no_impact") and detail and detail["stale_in_sentence"]:
        # 원문에서 사라진 날짜가 아직 원고 문장에 남아 있으면 '반영 완료·영향 없음'으로 닫을 수 없다(과거 내용을 현재 사실로 남기지 않는다)
        in_body = ai_evidence.normalize(ins.final_text) in ai_evidence.normalize(manuscript.body or "")
        if in_body:
            raise HTTPException(status_code=422, detail=f"원고에 아직 이전 원문 기준 날짜({', '.join(detail['stale_in_sentence'])})가 남아 있습니다 — 문장을 먼저 수정하거나 '추가 확인 필요'를 선택하세요")
    history = json.loads(ins.review_history_json or "[]")
    history.append({"resolution": resolution, "label": RESOLUTIONS[resolution], "note": note.strip(), "reviewer_id": str(user.id), "reviewed_at": _now().isoformat(),
                    "reviewed_source_hash": cur, "previous_baseline_hash": ins.baseline_hash})
    ins.review_history_json = json.dumps(history, ensure_ascii=False)
    ins.last_review_resolution, ins.last_review_note = resolution, note.strip()
    ins.last_reviewed_by_user_id, ins.last_reviewed_at, ins.last_review_hash = user.id, _now(), cur
    if resolution in ("updated", "no_impact"):
        ins.baseline_hash = cur  # 이 원문 버전까지 확인함 — 더 바뀌면 다시 표시된다
    elif resolution == "removed":
        ins.status = "removed"
    db.flush()
    return ins


# ---------------------------------------------------------------- 보고서·카드뉴스로의 전달 ----
def open_changes_for_manuscripts(db: Session, manuscript_ids: set[uuid.UUID]) -> list[dict]:
    out = []
    if not manuscript_ids:
        return out
    for ins in db.scalars(select(AIInsertion).where(AIInsertion.manuscript_id.in_(manuscript_ids), AIInsertion.status == "active")).all():
        if change_detail(db, ins) is not None:
            out.append({"id": str(ins.id), "title": f"AI 삽입 문장의 근거 원문이 변경됨: {ins.final_text[:50]}", "kind": "ai_source_change", "manuscript_id": str(ins.manuscript_id)})
    return out


def open_changes_for(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[dict]:
    """원고·보고서·카드뉴스에 전달할 '원문 변경·재검토 필요' 알림(연구원이 삽입 문장을 검토해 해소하기 전까지)."""
    from app.models.card_news import CardNews, CardNewsEvidence
    from app.models.report import ReportItem

    if entity_type == "manuscript":
        ids = {entity_id}
    elif entity_type == "report":
        ids = {i for i in db.scalars(select(ReportItem.manuscript_id).where(ReportItem.report_id == entity_id)).all() if i}
    else:
        cn = db.get(CardNews, entity_id)
        ids = {e.source_manuscript_id for e in db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == entity_id)).all() if e.source_manuscript_id}
        if cn is not None and cn.source_report_id:
            ids |= {i for i in db.scalars(select(ReportItem.manuscript_id).where(ReportItem.report_id == cn.source_report_id)).all() if i}
    return open_changes_for_manuscripts(db, ids)
