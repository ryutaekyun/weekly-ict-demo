"""공개 시연(GitHub Pages /preview/)용 읽기 전용 JSON 스냅샷 생성.

포함하는 것(허용 목록 방식 — 필드를 하나씩 명시한다):
- 공개된 공식 문서의 메타데이터: 제목·발행기관·국가·발표일·분야·자료유형·원문 URL(+링크 상태)·원문 확보 여부(예/아니오)
- 규칙 기반으로 묶은 이슈의 문서 목록·타임라인(유형·날짜만)
- 후보주제의 제목·분야·설명·추천 점수·'내부 검토 상태'(IITP 공식 선정 아님 표시)

포함하지 않는 것(구조상 읽어 오지 않음): 원문 전문·추출 텍스트(후보주제의 summary 필드는 원문에서 뽑은 텍스트라 저자명·이메일이 들어 있어 제외), 연구원·검토자 개인정보, 검토의견, 계정·인증 정보, 비공개 원고·보고서·출력 파일,
수동 등록·테스트용 후보주제(근거 문서가 없는 것).
이 스냅샷은 수집 시점의 정적 복사본이며 실시간 수집 결과가 아니다(화면에 기준일을 표시한다).

실행: python -m app.export_public_snapshot [출력 JSON 경로]
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.candidate_scoring import CandidateRecommendationScore
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.enums import ClassificationRelevance, ExtractionStatus
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.issue_timeline_event import IssueTimelineEvent
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.link_quality import classify_url

FIELD_LABELS = {
    "soc": "디지털사회혁신", "net": "통신·네트워크", "bcast": "방송·전파·위성", "sw": "SW·자율주행", "ai": "인공지능·데이터",
    "content": "콘텐츠·미디어", "sec": "보안·블록체인", "semi": "반도체·양자", "conv": "ICT 융합기술",
}
DOC_TYPE_LABELS = {
    "policy": "정부 정책", "law": "법령·규제", "paper": "학술논문", "report": "연구보고서", "standard": "기술표준", "statistics": "통계·분석자료",
    "press_release": "보도자료", "tech_announcement": "기업 기술발표", "news": "언론 보도", "other": "기타",
}
CANDIDATE_STATUS_LABELS = {"rec": "추천", "review": "검토중", "hold": "보류", "final": "내부 확정", "rejected": "반려"}
SAFE_URL = re.compile(r"^https?://", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class PrivacyError(Exception):
    """스냅샷에 이메일 등 개인 연락처가 남아 있으면 공개하지 않는다."""


def _scrub(value):
    """모든 문자열에서 이메일 주소를 지운다(원문 제목 등에 섞여 들어올 수 있는 개인 연락처의 마지막 방어선)."""
    if isinstance(value, str):
        return EMAIL.sub("", value).strip()
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


def assert_no_personal_data(snapshot: dict) -> None:
    text = json.dumps(snapshot, ensure_ascii=False)
    found = EMAIL.findall(text)
    if found:
        raise PrivacyError(f"스냅샷에 이메일 주소가 남아 있습니다: {found[:3]}")
TEST_MARKERS = ("E2E", "e2e-", "[시범]", "[합성")  # 테스트·시범 데이터는 공개 시연 목록에서 제외한다


def _day(dt) -> str | None:
    return dt.date().isoformat() if dt else None


def build_snapshot(db: Session) -> dict:
    docs_out: list[dict] = []
    included_ids: set = set()
    rows = db.execute(
        select(SourceDocument, DocumentClassification, DocumentFullText, Source)
        .join(DocumentClassification, DocumentClassification.document_id == SourceDocument.id)
        .outerjoin(DocumentFullText, DocumentFullText.document_id == SourceDocument.id)
        .outerjoin(Source, Source.id == SourceDocument.source_id)
        .where(DocumentClassification.relevance == ClassificationRelevance.MATCHED)
    ).all()
    members = {m.document_id: m.issue_cluster_id for m in db.scalars(select(IssueClusterDocument)).all()}
    for doc, cls, ft, src in rows:
        if any(m in doc.title for m in TEST_MARKERS):
            continue
        url = doc.origin_url if doc.origin_url and SAFE_URL.match(doc.origin_url.strip()) else ""
        link = classify_url(url)
        has_text = bool(ft and ft.extraction_status in (ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL))
        docs_out.append({
            "id": str(doc.id), "title": doc.title, "org": src.org_name if src else None, "country": doc.country_code,
            "published": _day(doc.published_at), "field": cls.primary_field_code.value if cls.primary_field_code else None,
            "type": doc.document_type.value, "url": url, "link_state": link["state"], "link_blocked": link["blocked"], "link_note": link["note"],
            "is_pdf": link["is_pdf"], "original_secured": has_text, "issue_id": str(members[doc.id]) if doc.id in members else None,
        })
        included_ids.add(doc.id)
    docs_out.sort(key=lambda d: (d["published"] or "", d["title"]), reverse=True)

    issue_ids = {m for d_id, m in members.items() if d_id in included_ids}
    issues_out = []
    for cluster in db.scalars(select(IssueCluster).where(IssueCluster.id.in_(issue_ids))).all() if issue_ids else []:
        mem = [m for m in db.scalars(select(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == cluster.id)).all() if m.document_id in included_ids]
        timeline = [{"type": t.event_type.value if hasattr(t.event_type, "value") else str(t.event_type), "date": _day(t.event_date), "document_id": str(t.document_id)}
                    for t in db.scalars(select(IssueTimelineEvent).where(IssueTimelineEvent.issue_cluster_id == cluster.id).order_by(IssueTimelineEvent.event_date)).all()
                    if t.document_id in included_ids]
        issues_out.append({
            "id": str(cluster.id), "title": cluster.title, "field": cluster.field_code.value, "last_activity": _day(cluster.last_activity_at),
            "documents": [{"id": str(m.document_id), "membership": m.membership_type.value} for m in mem], "timeline": timeline,
        })
    issues_out.sort(key=lambda i: i["last_activity"] or "", reverse=True)

    cands_out = []
    issue_set = {i["id"] for i in issues_out}
    for c in db.scalars(select(Candidate)).all():
        if not c.issue_cluster_id or str(c.issue_cluster_id) not in issue_set:
            continue  # 근거 이슈가 없는 수동 등록·테스트 후보주제는 제외
        if any(m in c.title for m in TEST_MARKERS):
            continue
        score = db.scalar(select(CandidateRecommendationScore).where(CandidateRecommendationScore.candidate_id == c.id))
        cands_out.append({
            "id": str(c.id), "title": c.title, "field": c.field_code.value, "announced": c.announced_date.isoformat() if c.announced_date else None,
            "org": c.source_org, "internal_status": CANDIDATE_STATUS_LABELS.get(c.status.value, c.status.value),
            "score": round(score.total_score, 1) if score and score.total_score is not None else None,
            "score_partial": bool(score and any(getattr(score, k) is None for k in ("policy_impact_score", "timeliness_score", "domestic_relevance_score", "novelty_score", "analysis_depth_score"))),
            "reason": c.recommended_reason, "issue_id": str(c.issue_cluster_id),
            "document_ids": [m["id"] for i in issues_out if i["id"] == str(c.issue_cluster_id) for m in i["documents"]],
        })

    counts = {code: sum(1 for d in docs_out if d["field"] == code) for code in FIELD_LABELS}
    snapshot = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_basis": "수집 시점의 정적 스냅샷입니다 — 실시간 수집 결과가 아닙니다. 공개된 공식 문서의 메타데이터와 규칙 기반 분류·이슈·후보 결과만 담았습니다.",
            "notice": "읽기 전용 공개 시연입니다. 로그인·저장·수정·파일 생성은 로컬 통합 웹사이트에서만 동작합니다. 후보주제의 '내부 검토 상태'는 IITP 공식 선정이 아닙니다.",
            "document_count": len(docs_out), "issue_count": len(issues_out), "candidate_count": len(cands_out),
            "published_min": min((d["published"] for d in docs_out if d["published"]), default=None),
            "published_max": max((d["published"] for d in docs_out if d["published"]), default=None),
        },
        "fields": [{"code": code, "label": label, "count": counts[code]} for code, label in FIELD_LABELS.items()],
        "doc_types": DOC_TYPE_LABELS,
        "documents": docs_out, "issues": issues_out, "candidates": cands_out,
    }
    snapshot = _scrub(snapshot)
    assert_no_personal_data(snapshot)
    return snapshot


def main() -> None:
    from app.core.db import SessionLocal

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        snap = build_snapshot(db)
    finally:
        db.close()
    out.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    m = snap["meta"]
    print(f"스냅샷 생성: 문서 {m['document_count']}건·이슈 {m['issue_count']}건·후보주제 {m['candidate_count']}건 → {out} ({out.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
