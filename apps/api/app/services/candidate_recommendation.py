"""IITP 보고서 후보주제 자동 추천 — 가중 점수 산출.

원칙: 근거가 부족한 평가 항목은 임의로 점수를 매기지 않고 None("평가 보류")으로 남긴다.
총점은 평가된 항목끼리만 가중치를 재정규화해 계산한다 — 평가 보류 항목을 0점으로 취급해
불공정하게 감점하지 않기 위함이다(reasoning에 어떤 항목이 보류됐는지 명시).
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.candidate_scoring import CandidateRecommendationScore, CandidateScoringConfig, DEFAULT_WEIGHTS
from app.models.document_full_text import DocumentFullText
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.enums import CandidateStatus, ClassificationMethod, UsageValueRating
from app.models.issue_analysis import IssueAnalysis
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.value_assessment import compute_recency_bucket

RATING_SCORE = {
    UsageValueRating.PRIORITY: 90.0,
    UsageValueRating.GENERAL: 60.0,
    UsageValueRating.NEEDS_MORE_INFO: 30.0,
    UsageValueRating.LOW_RELEVANCE: 0.0,
}
RECENCY_SCORE = {"within_7d": 100.0, "within_30d": 80.0, "within_90d": 55.0, "older": 25.0, "unknown": None}


def _member_documents(db: Session, cluster_id) -> list[SourceDocument]:
    members = db.query(IssueClusterDocument).filter(IssueClusterDocument.issue_cluster_id == cluster_id).all()
    return [db.get(SourceDocument, m.document_id) for m in members]


@dataclass
class ScoreResult:
    value: float | None
    reasoning: str


def get_or_create_scoring_config(db: Session) -> CandidateScoringConfig:
    config = db.query(CandidateScoringConfig).first()
    if config is None:
        config = CandidateScoringConfig()
        db.add(config)
        db.flush()
    return config


def _score_policy_impact(db: Session, docs: list[SourceDocument]) -> ScoreResult:
    best = None
    for doc in docs:
        va = db.query(DocumentValueAssessment).filter_by(document_id=doc.id).one_or_none()
        if va is None:
            continue
        score = RATING_SCORE.get(va.rating)
        if best is None or (score or -1) > best:
            best = score
    if best is None:
        return ScoreResult(None, "평가 보류 — 구성 문서에 실무 활용가치 판정 결과가 없음")
    return ScoreResult(best, f"구성 문서 중 최고 활용가치 등급 기준 점수({best:.0f}점)")


def _score_timeliness(docs: list[SourceDocument]) -> ScoreResult:
    latest = None
    for doc in docs:
        if doc.published_at and (latest is None or doc.published_at > latest):
            latest = doc.published_at
    if latest is None:
        return ScoreResult(None, "평가 보류 — 발표일을 확인할 수 없음")
    bucket = compute_recency_bucket(latest)
    score = RECENCY_SCORE.get(bucket)
    if score is None:
        return ScoreResult(None, "평가 보류 — 시의성 구간을 판정할 수 없음")
    return ScoreResult(score, f"최근 발표일 기준 시의성 구간={bucket}")


def _score_domestic_relevance(analysis: IssueAnalysis | None) -> ScoreResult:
    if analysis is None or not analysis.domestic_has_sufficient_basis:
        return ScoreResult(None, "평가 보류 — 국내 산업 연관성을 뒷받침할 근거가 부족함(원문에 없는 연관성을 추정하지 않음)")
    return ScoreResult(70.0, "국내 산업 연관성 근거가 확인됨(국내 시사점 분석 참고)")


def _score_novelty(db: Session, cluster: IssueCluster) -> ScoreResult:
    title_tokens = set(re.findall(r"[a-zA-Z가-힣]{4,}", cluster.title.lower()))
    existing = (
        db.query(Candidate)
        .filter(
            Candidate.status != CandidateStatus.REJECTED,
            # SQL에서 NULL != x는 거짓으로 취급돼 issue_cluster_id가 NULL인 후보(클러스터 없이
            # 수동 등록된 기존 후보주제)가 중복검사에서 빠지는 실수를 막는다.
            (Candidate.issue_cluster_id.is_(None)) | (Candidate.issue_cluster_id != cluster.id),
        )
        .all()
    )
    max_overlap = 0.0
    overlapping_title = None
    for c in existing:
        other_tokens = set(re.findall(r"[a-zA-Z가-힣]{4,}", c.title.lower()))
        if not other_tokens or not title_tokens:
            continue
        overlap = len(title_tokens & other_tokens) / len(title_tokens | other_tokens)
        if overlap > max_overlap:
            max_overlap = overlap
            overlapping_title = c.title
    score = max(0.0, 100.0 * (1 - max_overlap))
    if max_overlap > 0.3:
        return ScoreResult(score, f"기존 후보주제 '{overlapping_title}'와 제목 유사도 {max_overlap:.2f} — 중복 가능성 있음")
    return ScoreResult(score, "기존 후보주제와 뚜렷한 중복 없음")


def _score_analysis_depth(db: Session, docs: list[SourceDocument]) -> ScoreResult:
    total_chars = 0
    structured_count = 0
    for doc in docs:
        ft = db.query(DocumentFullText).filter_by(document_id=doc.id).one_or_none()
        if ft and ft.full_text:
            total_chars += ft.char_count
        se = db.query(DocumentStructuredExtract).filter_by(document_id=doc.id).one_or_none()
        if se and se.key_content:
            structured_count += 1
    # 문서 수·전문 확보량·구조화 완료 여부를 조합한 객관적 완성도 지표(해석이 아니라 집계)
    doc_count_score = min(40.0, len(docs) * 20.0)
    text_score = min(40.0, total_chars / 2000)
    structured_score = min(20.0, structured_count * 20.0)
    total = doc_count_score + text_score + structured_score
    return ScoreResult(
        total,
        f"구성 문서 {len(docs)}건, 확보 전문 {total_chars:,}자, 구조화 완료 {structured_count}건 기준 집계",
    )


def run_candidate_recommendation(
    db: Session, cluster: IssueCluster, *, created_by_user_id
) -> tuple[Candidate, CandidateRecommendationScore] | None:
    docs = _member_documents(db, cluster.id)
    if not docs:
        return None

    # 관련성 낮은 자료만 있는 클러스터는 후보로 추천하지 않는다
    ratings = [db.query(DocumentValueAssessment).filter_by(document_id=d.id).one_or_none() for d in docs]
    ratings = [r.rating for r in ratings if r is not None]
    if ratings and all(r == UsageValueRating.LOW_RELEVANCE for r in ratings):
        return None

    analysis = db.query(IssueAnalysis).filter_by(issue_cluster_id=cluster.id).one_or_none()

    policy = _score_policy_impact(db, docs)
    timeliness = _score_timeliness(docs)
    domestic = _score_domestic_relevance(analysis)
    novelty = _score_novelty(db, cluster)
    depth = _score_analysis_depth(db, docs)

    config = get_or_create_scoring_config(db)
    weights = {
        "policy_impact": config.policy_impact_weight,
        "timeliness": config.timeliness_weight,
        "domestic_relevance": config.domestic_relevance_weight,
        "novelty": config.novelty_weight,
        "analysis_depth": config.analysis_depth_weight,
    }
    scores = {
        "policy_impact": policy.value, "timeliness": timeliness.value,
        "domestic_relevance": domestic.value, "novelty": novelty.value, "analysis_depth": depth.value,
    }
    available = {k: v for k, v in scores.items() if v is not None}
    if available:
        weight_sum = sum(weights[k] for k in available)
        total_score = sum(weights[k] * v for k, v in available.items()) / weight_sum if weight_sum else None
    else:
        total_score = None

    reasoning = {
        "policy_impact": policy.reasoning, "timeliness": timeliness.reasoning,
        "domestic_relevance": domestic.reasoning, "novelty": novelty.reasoning, "analysis_depth": depth.reasoning,
        "skipped_criteria": [k for k, v in scores.items() if v is None],
    }

    representative = docs[0]
    source = db.get(Source, representative.source_id)
    latest_doc = max((d for d in docs if d.published_at), key=lambda d: d.published_at, default=representative)

    candidate = db.query(Candidate).filter_by(issue_cluster_id=cluster.id).one_or_none()
    if candidate is None:
        candidate = Candidate(
            field_code=cluster.field_code,
            issue_cluster_id=cluster.id,
            title=cluster.title,
            summary=analysis.key_summary if analysis else None,
            source_document_id=cluster.representative_document_id,
            announced_date=latest_doc.published_at.date() if latest_doc.published_at else None,
            source_org=source.org_name if source else None,
            recommended_reason=(
                f"규칙 기반 추천(AI 미설정) — 종합점수 {total_score:.1f}점"
                if total_score is not None
                else "규칙 기반 추천(AI 미설정) — 평가 근거 부족으로 종합점수 보류"
            ),
            status=CandidateStatus.REC,
            created_by_user_id=created_by_user_id,
        )
        db.add(candidate)
        db.flush()

    score_row = db.query(CandidateRecommendationScore).filter_by(candidate_id=candidate.id).one_or_none()
    if score_row is None:
        score_row = CandidateRecommendationScore(candidate_id=candidate.id)
        db.add(score_row)

    score_row.issue_cluster_id = cluster.id
    score_row.policy_impact_score = policy.value
    score_row.timeliness_score = timeliness.value
    score_row.domestic_relevance_score = domestic.value
    score_row.novelty_score = novelty.value
    score_row.analysis_depth_score = depth.value
    score_row.total_score = total_score
    score_row.weights_snapshot_json = json.dumps(weights, ensure_ascii=False)
    score_row.reasoning_json = json.dumps(reasoning, ensure_ascii=False)
    score_row.duplicate_check_json = json.dumps({"max_title_overlap_note": novelty.reasoning}, ensure_ascii=False)
    score_row.method = ClassificationMethod.RULE_BASED
    score_row.scored_at = datetime.now(timezone.utc)
    db.flush()

    return candidate, score_row
