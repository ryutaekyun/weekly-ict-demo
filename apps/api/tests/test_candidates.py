from app.models.enums import UserRole
from tests.conftest import auth_headers, make_user


def _create_candidate(client, headers, **overrides):
    payload = {
        "field_code": "net",
        "title": "일본 총무성, 로컬 5G 주파수 추가 할당 공고",
        "summary": "국내 통신사 영향 확인 필요",
        "source_org": "MIC Japan",
        "recommended_reason": "통신 분야 정책 변화",
    }
    payload.update(overrides)
    return client.post("/candidates", json=payload, headers=headers)


def test_create_and_get_candidate(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")

    resp = _create_candidate(client, headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "일본 총무성, 로컬 5G 주파수 추가 할당 공고"
    assert body["status"] == "rec"

    detail = client.get(f"/candidates/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["reviews"] == []


def test_create_candidate_requires_auth(client):
    resp = client.post("/candidates", json={"field_code": "net", "title": "x"})
    assert resp.status_code == 401


def test_list_candidates_filters_by_field_and_search(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")
    _create_candidate(client, headers, field_code="net", title="5G 주파수 할당")
    _create_candidate(client, headers, field_code="ai", title="생성형 AI 모델 공개")

    resp = client.get("/candidates", params={"field_code": "ai"}, headers=headers)
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()]
    assert titles == ["생성형 AI 모델 공개"]

    resp = client.get("/candidates", params={"q": "5G"}, headers=headers)
    assert [c["title"] for c in resp.json()] == ["5G 주파수 할당"]


def test_researcher_can_add_review_comment(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")
    candidate_id = _create_candidate(client, headers).json()["id"]

    resp = client.post(
        f"/candidates/{candidate_id}/reviews",
        json={"comment_text": "국내 통신사 대응 현황 확인 후 추천 상정"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_final_approval"] is False

    detail = client.get(f"/candidates/{candidate_id}", headers=headers).json()
    assert len(detail["reviews"]) == 1
    assert detail["status"] == "rec"  # 일반 의견은 상태를 바꾸지 않음


def test_researcher_cannot_submit_final_approval(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")
    candidate_id = _create_candidate(client, headers).json()["id"]

    resp = client.post(
        f"/candidates/{candidate_id}/reviews",
        json={"comment_text": "확정합니다", "is_final_approval": True, "decided_status": "final"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_approver_can_finalize_candidate(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    make_user(db_session, "approver@example.com", UserRole.APPROVER, "허선양")
    headers = auth_headers(client, "researcher@example.com")
    candidate_id = _create_candidate(client, headers).json()["id"]

    approver_headers = auth_headers(client, "approver@example.com")
    resp = client.post(
        f"/candidates/{candidate_id}/reviews",
        json={
            "comment_text": "국내 통신사 영향 확인됨. 이번 주 후보로 확정.",
            "is_final_approval": True,
            "decided_status": "final",
        },
        headers=approver_headers,
    )
    assert resp.status_code == 201, resp.text

    detail = client.get(f"/candidates/{candidate_id}", headers=headers).json()
    assert detail["status"] == "final"
    assert detail["reviews"][0]["is_final_approval"] is True


def test_status_change_to_final_via_patch_requires_approver(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")
    candidate_id = _create_candidate(client, headers).json()["id"]

    resp = client.patch(f"/candidates/{candidate_id}", json={"status": "final"}, headers=headers)
    assert resp.status_code == 403

    resp = client.patch(f"/candidates/{candidate_id}", json={"status": "hold"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "hold"


def test_delete_candidate_only_by_owner_or_admin(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    make_user(db_session, "other@example.com", UserRole.RESEARCHER)
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "researcher@example.com")
    candidate_id = _create_candidate(client, headers).json()["id"]

    other_headers = auth_headers(client, "other@example.com")
    resp = client.delete(f"/candidates/{candidate_id}", headers=other_headers)
    assert resp.status_code == 403

    admin_headers = auth_headers(client, "admin@example.com")
    resp = client.delete(f"/candidates/{candidate_id}", headers=admin_headers)
    assert resp.status_code == 204

    resp = client.get(f"/candidates/{candidate_id}", headers=headers)
    assert resp.status_code == 404
