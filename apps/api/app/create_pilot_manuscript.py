"""Phase 3-1 시범 작성 원고 1건 생성 — 실제 수집한 공식 원문(연방관보 FMVSS 305a NPRM·Final Rule)만 사용한다.

- 실제 IITP 발간 완료 원고가 아니라 기능 시연·검증용 '시범 작성 원고'(is_pilot=True)다.
- 원문에서 확인되지 않은 내용은 쓰지 않고 '추가 조사 필요'로 남긴다(국내 산업 시사점 등).
- 각주 발췌문은 원문 전문과 대조해 일치할 때만 연구원 검증(검토자)으로 MATCHED 처리한다.
- 페이지·문단 위치는 추적하지 않았으므로 location_label을 비워 '위치 미확인'으로 둔다.

실행: python -m app.create_pilot_manuscript   (dev-researcher-1=작성자, dev-reviewer-1=검토자 더미 계정 필요)
"""

import json
import uuid

from app.core.db import SessionLocal
from app.models.candidate import Candidate
from app.models.document_full_text import DocumentFullText
from app.models.enums import EvidenceMatchStatus
from app.models.issue_cluster import IssueCluster
from app.models.manuscript import Manuscript
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services import manuscript_comment_service, manuscript_footnote_service, manuscript_service

PILOT_TITLE = "[시범] 미국 NHTSA 전기차 동력계 안전기준(FMVSS 305a) 제정 동향"

# (키, 문서 제목 일부, 발췌문)
ANCHORS = {
    "nprm_scope": "미국 NHTSA는 2024.4.15. 기존 FMVSS No. 305를 대체하는 FMVSS No. 305a 제정안(NPRM, Docket NHTSA-2024-0012, RIN 2127-AM43)을 공고함",
    "nprm_comment": "의견수렴 마감은 2024.6.14.이었음",
    "final_effective": "최종 규정은 2025.2.18.부터 시행됨",
    "final_emergency": "비상대응정보 문서화 요건의 준수 시한은 2025.12.22.임",
    "final_light": "총중량 4,536kg 이하 차량의 그 밖의 요건 준수 시한은 2027.9.1.임",
}

EXCERPTS = {
    "nprm_scope": ("Proposed Rules", "NHTSA proposes to establish Federal Motor Vehicle Safety Standard (FMVSS) No. 305a to replace FMVSS No. 305"),
    "nprm_comment": ("Proposed Rules", "Comments should be submitted no later than June 14, 2024."),
    "final_effective": ("Rules and Regulations", "This final rule is effective February 18, 2025."),
    "final_emergency": ("Rules and Regulations", "compliance date is December 22, 2025, for the emergency response documentation requirements"),
    "final_light": ("Rules and Regulations", "the compliance date is September 1, 2027, for vehicles with a gross vehicle weight rating of 4,536 kilograms (kg) or less"),
}


def _norm(s: str) -> str:
    return " ".join(s.split())


def _text(content: str, footnote_id: str | None = None) -> dict:
    node = {"type": "text", "text": content}
    if footnote_id:
        node["marks"] = [{"type": "footnoteMark", "attrs": {"footnoteId": footnote_id}}]
    return node


def _para(*nodes: dict) -> dict:
    return {"type": "paragraph", "content": list(nodes)}


def _heading(level: int, content: str) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [_text(content)]}


def _plain(doc: dict) -> str:
    out: list[str] = []

    def walk(n: dict) -> None:
        if n.get("type") == "text":
            out.append(n["text"])
        for c in n.get("content", []):
            walk(c)
        if n.get("type") in ("paragraph", "heading"):
            out.append("\n")

    walk(doc)
    return "".join(out).strip()


def main() -> None:
    db = SessionLocal()
    try:
        author = db.query(User).filter_by(email="dev-researcher-1@example.com").one()
        reviewer = db.query(User).filter_by(email="dev-reviewer-1@example.com").one()

        if db.query(Manuscript).filter_by(title=PILOT_TITLE).first():
            raise SystemExit("시범 원고가 이미 있습니다 — 중복 생성하지 않습니다.")

        cluster = db.query(IssueCluster).filter(IssueCluster.title.like("%FMVSS No. 305a%")).first()
        candidate = db.query(Candidate).filter_by(issue_cluster_id=cluster.id).first()

        docs = {}
        for key, (needle, _) in EXCERPTS.items():
            if needle not in docs:
                docs[needle] = None
        from app.models.issue_cluster_document import IssueClusterDocument

        for m in db.query(IssueClusterDocument).filter_by(issue_cluster_id=cluster.id).all():
            d = db.get(SourceDocument, m.document_id)
            ft = db.query(DocumentFullText).filter_by(document_id=d.id).one()
            full = _norm(ft.full_text or "")
            if "Proposed Rules" in full[:300]:
                docs["Proposed Rules"] = (d, full)
            elif "Rules and Regulations" in full[:300]:
                docs["Rules and Regulations"] = (d, full)

        manuscript = manuscript_service.create_manuscript(
            db, author_user_id=author.id, title=PILOT_TITLE, manuscript_type="key_issue",
            candidate_id=candidate.id if candidate else None, is_pilot=True,
        )
        manuscript.title_en = "[Pilot] NHTSA FMVSS No. 305a - Electric Powertrain Integrity"

        footnote_ids: dict[str, str] = {}
        footnotes = {}
        for key, (needle, excerpt) in EXCERPTS.items():
            d, full = docs[needle]
            mark_id = str(uuid.uuid4())
            footnote_ids[key] = mark_id
            footnotes[key] = manuscript_footnote_service.create_footnote(
                db, manuscript_id=manuscript.id, created_by_user_id=author.id, mark_id=mark_id,
                anchor_text=ANCHORS[key], source_url=d.origin_url, source_document_id=d.id,
                source_org="미국 국가도로교통안전청(NHTSA)", excerpt=excerpt, location_label=None,
                published_at=d.published_at,
            )

        # v1 — 초안: 배경·주요 내용만 작성, 국내 시사점은 근거가 없어 '추가 조사 필요'로 남김
        doc_v1 = {"type": "doc", "content": [
            _heading(1, "미국 NHTSA 전기차 동력계 안전기준(FMVSS 305a) 제정 동향"),
            _heading(2, "1. 추진 경과"),
            _para(
                _text("미국 NHTSA는 2024.4.15. 기존 FMVSS No. 305를 대체하는 FMVSS No. 305a 제정안(NPRM, Docket NHTSA-2024-0012, RIN 2127-AM43)을 공고함", footnote_ids["nprm_scope"]),
                _text(". 의견수렴 마감은 2024.6.14.이었음", footnote_ids["nprm_comment"]),
                _text("."),
            ),
            _para(_text("2024.12.20. 동일 RIN으로 최종 규정(Docket NHTSA-2024-0091)이 공고됨.")),
            _heading(2, "2. 주요 내용 및 일정"),
            _para(
                _text("최종 규정은 2025.2.18.부터 시행됨", footnote_ids["final_effective"]),
                _text(". 비상대응정보 문서화 요건의 준수 시한은 2025.12.22.임", footnote_ids["final_emergency"]),
                _text("."),
            ),
            _para(_text("총중량 4,536kg 이하 차량의 그 밖의 요건 준수 시한은 2027.9.1.임", footnote_ids["final_light"]), _text(". 중량 초과 차량의 시한은 별도 확인 후 보완 예정임.")),
            _heading(2, "3. 국내 산업 시사점"),
            _para(_text("추가 조사 필요 — 원문에 국내 산업 영향을 직접 뒷받침하는 근거가 없어 작성하지 않음.")),
        ]}
        manuscript_service.update_manuscript_body(
            db, manuscript, title=None, title_en=None, body_json=json.dumps(doc_v1, ensure_ascii=False),
            body=_plain(doc_v1), lock_version=manuscript.lock_version, actor_user_id=author.id,
            change_note="1차 초안(시범)", is_milestone=True,
        )

        # 검토 요청 → 검토자 수정요청
        manuscript_service.request_review(db, manuscript, reviewer_user_id=reviewer.id)
        manuscript_service.request_changes(db, manuscript)
        review_comment = manuscript_comment_service.create_comment(
            db, manuscript_id=manuscript.id, author_user_id=reviewer.id,
            comment_text="의견수렴·시행·준수 시한의 날짜 구분을 명확히 하고, 근거가 없는 부분은 '추가 조사 필요'를 유지해주세요.",
            anchor_text="2. 주요 내용 및 일정",
        )

        # v2 — 수정: 날짜 구분 문장 보강
        doc_v2 = json.loads(json.dumps(doc_v1))
        doc_v2["content"].insert(5, _para(_text("※ 날짜 구분: 의견수렴 마감(2024.6.14.) → 최종 규정 공고(2024.12.20.) → 시행일(2025.2.18.) → 준수 시한(2025.12.22. / 2027.9.1.)임.")))
        manuscript_service.update_manuscript_body(
            db, manuscript, title=None, title_en=None, body_json=json.dumps(doc_v2, ensure_ascii=False),
            body=_plain(doc_v2), lock_version=manuscript.lock_version, actor_user_id=author.id,
            change_note="검토 의견 반영 — 날짜 구분 보강", is_milestone=True,
        )
        manuscript_comment_service.resolve_comment(db, review_comment, resolver_user_id=author.id)
        manuscript_service.request_review(db, manuscript, reviewer_user_id=reviewer.id)

        # 각주 검증: 발췌문이 원문 전문에 그대로 있을 때만 검토자가 MATCHED 처리. 하나는 일부러 미검증으로 남김
        verified = 0
        for key, fn in footnotes.items():
            d, full = docs[EXCERPTS[key][0]]
            if key == "final_light":
                continue
            if _norm(EXCERPTS[key][1]) in full:
                fn.verification_status = EvidenceMatchStatus.MATCHED
                fn.verified_by_user_id = reviewer.id
                from datetime import datetime, timezone
                fn.verified_at = datetime.now(timezone.utc)
                verified += 1

        db.commit()
        print(f"시범 원고 생성 완료: id={manuscript.id}, 각주 {len(footnotes)}건(검증 {verified}건), 상태={manuscript.status.value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
