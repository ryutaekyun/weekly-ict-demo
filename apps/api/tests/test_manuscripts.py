from datetime import datetime, timezone

from app.models.candidate import Candidate
from app.models.enums import ClusterReviewStatus, FieldCode, UserRole
from app.models.issue_cluster import IssueCluster
from tests.conftest import auth_headers, make_user


def _make_candidate(db_session, *, with_issue_needs_review=False):
    cluster = IssueCluster(
        title="Test Issue", field_code=FieldCode.AI, first_seen_at=datetime.now(timezone.utc),
        review_status=ClusterReviewStatus.NEEDS_REVIEW if with_issue_needs_review else ClusterReviewStatus.CONFIRMED,
    )
    db_session.add(cluster)
    db_session.commit()
    db_session.refresh(cluster)

    from app.models.user import User

    creator = db_session.query(User).filter_by(email="researcher-a@example.com").one_or_none()
    if creator is None:
        creator = make_user(db_session, "researcher-a@example.com", UserRole.RESEARCHER)

    candidate = Candidate(
        field_code=FieldCode.AI, title="AI 정책 변화", status="final",
        issue_cluster_id=cluster.id, created_by_user_id=creator.id,
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate, cluster


def test_create_manuscript_requires_auth(client, db_session):
    resp = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "제목"})
    assert resp.status_code == 401


def test_create_manuscript_from_candidate_and_fetch_context(client, db_session):
    make_user(db_session, "researcher1@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher1@example.com")
    candidate, cluster = _make_candidate(db_session)

    resp = client.post(
        "/manuscripts",
        json={"candidate_id": str(candidate.id), "manuscript_type": "key_issue", "title": candidate.title},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    manuscript_id = body["id"]
    assert body["status"] == "draft"
    assert body["lock_version"] == 0
    assert body["needs_reexamination"]["flagged"] is False

    ctx = client.get(f"/manuscripts/{manuscript_id}/context", headers=headers)
    assert ctx.status_code == 200
    assert ctx.json()["candidate"]["title"] == "AI 정책 변화"
    assert ctx.json()["issue"]["cluster"]["title"] == "Test Issue"


def test_needs_reexamination_flagged_when_cluster_needs_review(client, db_session):
    make_user(db_session, "researcher2@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher2@example.com")
    candidate, _ = _make_candidate(db_session, with_issue_needs_review=True)

    resp = client.post(
        "/manuscripts",
        json={"candidate_id": str(candidate.id), "manuscript_type": "key_issue", "title": candidate.title},
        headers=headers,
    )
    assert resp.json()["needs_reexamination"]["flagged"] is True
    assert "검토대기" in resp.json()["needs_reexamination"]["reason"]


def test_update_body_saves_and_persists_after_refetch(client, db_session):
    make_user(db_session, "researcher3@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher3@example.com")
    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=headers)
    mid = create.json()["id"]

    resp = client.patch(
        f"/manuscripts/{mid}",
        json={"body_json": '{"type":"doc","content":[]}', "body": "본문 내용", "lock_version": 0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["lock_version"] == 1
    assert resp.json()["body"] == "본문 내용"

    refetched = client.get(f"/manuscripts/{mid}", headers=headers)
    assert refetched.json()["body"] == "본문 내용"
    assert refetched.json()["lock_version"] == 1


def test_optimistic_lock_conflict_detected(client, db_session):
    """두 사용자가 동일 원고를 동시에 수정하면 낙관적 잠금으로 충돌이 감지되어야 한다."""
    make_user(db_session, "researcher4@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher4@example.com")
    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=headers)
    mid = create.json()["id"]

    first = client.patch(
        f"/manuscripts/{mid}",
        json={"body_json": '{"a":1}', "body": "첫 저장", "lock_version": 0},
        headers=headers,
    )
    assert first.status_code == 200

    # 과거 lock_version(0)으로 다시 저장 시도 — 이미 1로 올라갔으므로 충돌해야 한다
    conflict = client.patch(
        f"/manuscripts/{mid}",
        json={"body_json": '{"b":2}', "body": "충돌 저장", "lock_version": 0},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_version_milestone_save_and_restore(client, db_session):
    make_user(db_session, "researcher5@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher5@example.com")
    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=headers)
    mid = create.json()["id"]

    v1 = client.patch(
        f"/manuscripts/{mid}",
        json={"body_json": '{"v":1}', "body": "버전1 내용", "lock_version": 0, "is_milestone": True, "change_note": "초안"},
        headers=headers,
    )
    assert v1.status_code == 200

    v2 = client.patch(
        f"/manuscripts/{mid}",
        json={"body_json": '{"v":2}', "body": "버전2 내용", "lock_version": 1, "is_milestone": True, "change_note": "수정본"},
        headers=headers,
    )
    assert v2.status_code == 200

    versions = client.get(f"/manuscripts/{mid}/versions", headers=headers).json()
    assert len(versions) == 2
    v1_id = [v for v in versions if v["change_note"] == "초안"][0]["id"]

    restored = client.post(f"/manuscripts/{mid}/versions/{v1_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["body"] == "버전1 내용"

    refetched = client.get(f"/manuscripts/{mid}", headers=headers)
    assert refetched.json()["body"] == "버전1 내용"


def test_full_review_workflow_draft_to_approved(client, db_session):
    author = make_user(db_session, "author1@example.com", UserRole.RESEARCHER)
    reviewer = make_user(db_session, "reviewer-x@example.com", UserRole.REVIEWER)
    approver = make_user(db_session, "approver-x@example.com", UserRole.APPROVER)

    author_headers = auth_headers(client, "author1@example.com")
    reviewer_headers = auth_headers(client, "reviewer-x@example.com")
    approver_headers = auth_headers(client, "approver-x@example.com")

    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=author_headers)
    mid = create.json()["id"]

    # 작성자가 검토 요청
    req = client.post(
        f"/manuscripts/{mid}/review-request", json={"reviewer_user_id": str(reviewer.id)}, headers=author_headers,
    )
    assert req.status_code == 200
    assert req.json()["status"] == "review_requested"

    # 검토자가 수정 요청(의견 포함) — 작성자는 request-changes 권한 없음
    denied = client.post(
        f"/manuscripts/{mid}/request-changes", json={"comment_text": "근거 보강 필요"}, headers=author_headers,
    )
    assert denied.status_code == 403

    changes = client.post(
        f"/manuscripts/{mid}/request-changes", json={"comment_text": "근거 보강 필요"}, headers=reviewer_headers,
    )
    assert changes.status_code == 200
    assert changes.json()["status"] == "changes_requested"

    comments = client.get(f"/manuscripts/{mid}/comments", headers=author_headers).json()
    assert len(comments) == 1
    assert comments[0]["comment_text"] == "근거 보강 필요"

    # 작성자가 의견 해결 처리 후 재검토 요청
    resolve = client.post(f"/manuscripts/{mid}/comments/{comments[0]['id']}/resolve", headers=author_headers)
    assert resolve.json()["status"] == "resolved"

    reresub = client.post(
        f"/manuscripts/{mid}/review-request", json={"reviewer_user_id": str(reviewer.id)}, headers=author_headers,
    )
    assert reresub.status_code == 200

    # 일반 연구원은 최종 승인 불가
    forbidden_approve = client.post(f"/manuscripts/{mid}/approve", json={}, headers=reviewer_headers)
    assert forbidden_approve.status_code == 403

    approved = client.post(f"/manuscripts/{mid}/approve", json={"comment": "최종 확인 완료"}, headers=approver_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # 승인된 원고는 일반 저장으로 무단 수정할 수 없다
    blocked_edit = client.patch(
        f"/manuscripts/{mid}",
        json={"body_json": "{}", "body": "무단수정 시도", "lock_version": approved.json()["lock_version"]},
        headers=author_headers,
    )
    assert blocked_edit.status_code == 409

    # approver가 재검토로 되돌리면 다시 편집 가능
    reopened = client.post(f"/manuscripts/{mid}/reopen", headers=approver_headers)
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "changes_requested"


def test_iitp_selection_recorded_separately_from_internal_approval(client, db_session):
    make_user(db_session, "approver-y@example.com", UserRole.APPROVER)
    make_user(db_session, "researcher-y@example.com", UserRole.RESEARCHER)
    approver_headers = auth_headers(client, "approver-y@example.com")
    researcher_headers = auth_headers(client, "researcher-y@example.com")

    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=researcher_headers)
    mid = create.json()["id"]
    assert create.json()["iitp_selection_status"] == "not_submitted"

    denied = client.patch(
        f"/manuscripts/{mid}/iitp-selection",
        json={"iitp_selection_status": "selected", "iitp_selection_note": "최종 채택"},
        headers=researcher_headers,
    )
    assert denied.status_code == 403

    updated = client.patch(
        f"/manuscripts/{mid}/iitp-selection",
        json={"iitp_selection_status": "selected", "iitp_selection_note": "최종 채택"},
        headers=approver_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["iitp_selection_status"] == "selected"
    # 내부 승인 상태는 그대로 draft — IITP 선정과 내부 확정은 독립적으로 관리된다
    assert updated.json()["status"] == "draft"


def test_footnote_defaults_to_not_verified_and_requires_explicit_confirmation(client, db_session):
    make_user(db_session, "researcher6@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher6@example.com")
    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=headers)
    mid = create.json()["id"]

    fn = client.post(
        f"/manuscripts/{mid}/footnotes",
        json={
            "mark_id": "fn-1", "anchor_text": "주요 수치 인용", "source_url": "https://example.gov/doc1",
            "excerpt": "원문 발췌문", "location_label": None,
        },
        headers=headers,
    )
    assert fn.status_code == 201
    assert fn.json()["verification_status"] == "not_verified"
    fid = fn.json()["id"]

    verified = client.post(f"/manuscripts/{mid}/footnotes/{fid}/verify", params={"matched": True}, headers=headers)
    assert verified.json()["verification_status"] == "matched"
    assert verified.json()["verified_by_user_id"] is not None

    detail = client.get(f"/manuscripts/{mid}", headers=headers).json()
    assert detail["footnote_verification_total"] == 1
    assert detail["footnote_verification_verified"] == 1


def test_footnote_edit_resets_verification_to_not_verified(client, db_session):
    make_user(db_session, "researcher7@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher7@example.com")
    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=headers)
    mid = create.json()["id"]

    fn = client.post(
        f"/manuscripts/{mid}/footnotes",
        json={"mark_id": "fn-1", "anchor_text": "텍스트", "source_url": "https://example.gov/doc1"},
        headers=headers,
    )
    fid = fn.json()["id"]
    client.post(f"/manuscripts/{mid}/footnotes/{fid}/verify", params={"matched": True}, headers=headers)

    edited = client.patch(
        f"/manuscripts/{mid}/footnotes/{fid}", json={"excerpt": "수정된 발췌"}, headers=headers,
    )
    assert edited.json()["verification_status"] == "not_verified"


def test_only_author_can_edit_manuscript_body(client, db_session):
    make_user(db_session, "owner@example.com", UserRole.RESEARCHER)
    make_user(db_session, "stranger@example.com", UserRole.RESEARCHER)
    owner_headers = auth_headers(client, "owner@example.com")
    stranger_headers = auth_headers(client, "stranger@example.com")

    create = client.post("/manuscripts", json={"manuscript_type": "key_issue", "title": "원고"}, headers=owner_headers)
    mid = create.json()["id"]

    resp = client.patch(
        f"/manuscripts/{mid}", json={"body_json": "{}", "body": "남의 원고 수정", "lock_version": 0},
        headers=stranger_headers,
    )
    assert resp.status_code == 403
