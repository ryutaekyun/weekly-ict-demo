import json
from datetime import datetime, timezone

from app.models.candidate import Candidate
from app.models.candidate_scoring import CandidateRecommendationScore
from app.models.enums import ClassificationMethod, FieldCode, UserRole
from tests.conftest import auth_headers, make_user


def test_candidate_detail_includes_recommendation_score_when_present(client, db_session):
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    from app.models.user import User
    admin_user = db_session.query(User).filter_by(email="admin@example.com").one()

    candidate = Candidate(
        field_code=FieldCode.AI, title="AI 정책 변화", status="rec", created_by_user_id=admin_user.id,
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    score = CandidateRecommendationScore(
        candidate_id=candidate.id, policy_impact_score=80.0, timeliness_score=70.0,
        domestic_relevance_score=None, novelty_score=60.0, analysis_depth_score=50.0,
        total_score=65.0, weights_snapshot_json=json.dumps({"policy_impact": 0.3}),
        reasoning_json=json.dumps(
            {"domestic_relevance": "평가 보류 — 근거 부족", "skipped_criteria": ["domestic_relevance"]}, ensure_ascii=False
        ),
        method=ClassificationMethod.RULE_BASED, scored_at=datetime.now(timezone.utc),
    )
    db_session.add(score)
    db_session.commit()

    resp = client.get(f"/candidates/{candidate.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation_score"] is not None
    assert body["recommendation_score"]["total_score"] == 65.0
    assert body["recommendation_score"]["domestic_relevance_score"] is None
    assert "평가 보류" in body["recommendation_score"]["reasoning_json"]


def test_candidate_detail_score_null_when_not_scored(client, db_session):
    make_user(db_session, "admin2@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin2@example.com")
    from app.models.user import User
    admin_user = db_session.query(User).filter_by(email="admin2@example.com").one()

    candidate = Candidate(field_code=FieldCode.SEMI, title="반도체 이슈", status="rec", created_by_user_id=admin_user.id)
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    resp = client.get(f"/candidates/{candidate.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["recommendation_score"] is None
