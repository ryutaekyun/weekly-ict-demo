"""동일 이슈 자동 통합(클러스터링).

실데이터 관찰(2026-10-22): 이 데이터셋은 뉴스 매체가 같은 사건을 여러 번 보도하는 구조가
아니라, 연방관보(Federal Register) 공식 규제문서가 다수다. 같은 규제 조치는 시간이 지나며
NPRM(입법예고)→Final Rule(확정)처럼 "같은 RIN/Docket 번호"로 여러 건 발표되는 경우가 실제로
있었다(예: RIN 2127-AM43이 2024-04-15, 2024-12-20 두 건에 등장). 그래서 이 모듈은 RIN/Docket
번호 일치를 "동일 사건"의 1차 신호로 쓰고, 제목 유사도는 2차(약한) 신호로만 쓴다 — 키워드가
같다는 이유만으로 통합하지 않는다는 지시사항을 지키기 위함이다.

한 문서가 서로 다른 두 클러스터와 동시에 강하게 매칭되는 경우(예: 하나의 설명회가 서로 다른
두 RIN을 함께 다루는 경우)는 모호하다고 보고 "자동 통합하지 않고 검토 대기"로 둔다.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.enums import (
    ClassificationMethod,
    ClassificationRelevance,
    ClusterReviewStatus,
    FieldCode,
    IssueMembershipType,
)
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.issue_cluster_history import IssueClusterMembershipHistory
from app.models.source_document import SourceDocument

RIN_PATTERN = re.compile(r"RIN\s+(\d{4}[–\-]\w{2}\d{2,3})", re.IGNORECASE)
DOCKET_PATTERN = re.compile(r"Docket\s+No\.?\s*([A-Za-z]*[–\-]?\d[\w–\-]{2,})", re.IGNORECASE)

TITLE_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "of", "to", "in", "on", "a", "an",
    "notice", "notices", "rule", "rules", "final", "proposed", "agency", "information", "collection",
    "activities", "request", "comment", "comments", "department", "commission", "administration",
}
TITLE_WINDOW_DAYS = 180
TITLE_SIMILARITY_THRESHOLD = 0.5


@dataclass
class DocSignature:
    document_id: object
    published_at: datetime | None
    title_tokens: set
    rins: set
    dockets: set


@dataclass
class ClusterMatch:
    cluster_id: object
    reason: str
    score: float
    membership_type: IssueMembershipType
    ambiguous_with: list = field(default_factory=list)


def _title_tokens(title: str) -> set:
    words = re.findall(r"[a-zA-Z가-힣]{4,}", title.lower())
    return {w for w in words if w not in TITLE_STOPWORDS}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def build_signature(db: Session, document: SourceDocument) -> DocSignature:
    ft = db.query(DocumentFullText).filter_by(document_id=document.id).one_or_none()
    text = (ft.full_text if ft and ft.full_text else document.raw_text or "")[:4000]
    rins = {m.replace("–", "-") for m in RIN_PATTERN.findall(text)}
    dockets = {m.replace("–", "-") for m in DOCKET_PATTERN.findall(text) if len(m) >= 3}
    return DocSignature(
        document_id=document.id,
        published_at=document.published_at,
        title_tokens=_title_tokens(document.title),
        rins=rins,
        dockets=dockets,
    )


def _build_cluster_signatures(db: Session, clusters: list[IssueCluster]) -> list[tuple[IssueCluster, DocSignature]]:
    result = []
    for cluster in clusters:
        members = (
            db.query(IssueClusterDocument).filter(IssueClusterDocument.issue_cluster_id == cluster.id).all()
        )
        if not members:
            continue
        # 클러스터 전체의 rin/docket/제목토큰 합집합(멤버 중 하나라도 걸리면 매칭)
        combined_rins: set = set()
        combined_dockets: set = set()
        combined_tokens: set = set()
        latest_published: datetime | None = None
        for m in members:
            doc = db.get(SourceDocument, m.document_id)
            sig = build_signature(db, doc)
            combined_rins |= sig.rins
            combined_dockets |= sig.dockets
            combined_tokens |= sig.title_tokens
            if sig.published_at and (latest_published is None or sig.published_at > latest_published):
                latest_published = sig.published_at
        result.append(
            (
                cluster,
                DocSignature(
                    document_id=None, published_at=latest_published,
                    title_tokens=combined_tokens, rins=combined_rins, dockets=combined_dockets,
                ),
            )
        )
    return result


def find_candidate_clusters_global(db: Session) -> list[tuple[IssueCluster, DocSignature]]:
    """RIN/Docket 같은 강한 신호는 분야 분류 오차와 무관하게 전역에서 찾아야 한다 —
    같은 규제 조치가 문서마다 조금씩 다르게 분류될 수 있기 때문이다(실데이터에서 확인:
    동일 RIN의 두 문서가 각각 bcast/sw로 분류된 사례)."""
    clusters = db.scalars(select(IssueCluster)).all()
    return _build_cluster_signatures(db, clusters)


def find_candidate_clusters_same_field(db: Session, field_code: FieldCode) -> list[tuple[IssueCluster, DocSignature]]:
    """제목 유사도 같은 약한 신호는 분야가 같을 때만 비교한다 — 서로 다른 분야의 문서가
    우연히 제목 단어를 공유한다고 묶이지 않도록 하기 위함이다."""
    clusters = db.scalars(select(IssueCluster).where(IssueCluster.field_code == field_code)).all()
    return _build_cluster_signatures(db, clusters)


def match_document_to_clusters(
    sig: DocSignature,
    global_candidates: list[tuple[IssueCluster, DocSignature]],
    same_field_candidates: list[tuple[IssueCluster, DocSignature]],
) -> list[ClusterMatch]:
    strong_matches: list[ClusterMatch] = []
    for cluster, csig in global_candidates:
        if sig.rins and csig.rins and (sig.rins & csig.rins):
            shared = sig.rins & csig.rins
            strong_matches.append(
                ClusterMatch(
                    cluster_id=cluster.id,
                    reason=f"동일 RIN 번호 공유: {', '.join(sorted(shared))}",
                    score=1.0,
                    membership_type=IssueMembershipType.FOLLOW_UP,
                )
            )
            continue
        if sig.dockets and csig.dockets and (sig.dockets & csig.dockets):
            shared = sig.dockets & csig.dockets
            strong_matches.append(
                ClusterMatch(
                    cluster_id=cluster.id,
                    reason=f"동일 Docket 번호 공유: {', '.join(sorted(shared))}",
                    score=0.9,
                    membership_type=IssueMembershipType.FOLLOW_UP,
                )
            )
    if strong_matches:
        # 강한 신호가 하나라도 있으면 약한 신호(제목 유사도)는 보지 않는다 — 더 신뢰할 수 있는
        # 근거가 있는데 굳이 약한 근거까지 섞어 모호함을 늘리지 않기 위함.
        return strong_matches

    matches: list[ClusterMatch] = []
    for cluster, csig in same_field_candidates:
        # 양쪽 모두 RIN/Docket 번호가 확인되는데 서로 다르면, "이미 서로 다른 조치임이 확인된"
        # 경우다 — 지시사항이 명시적으로 경고한 "제목이 같다는 이유만으로 별개 조치를 합치는"
        # 실수를 막기 위해, 이때는 제목 유사도가 아무리 높아도 약한 신호 매칭을 적용하지 않는다.
        rins_conflict = bool(sig.rins) and bool(csig.rins) and not (sig.rins & csig.rins)
        dockets_conflict = bool(sig.dockets) and bool(csig.dockets) and not (sig.dockets & csig.dockets)
        if rins_conflict or dockets_conflict:
            continue

        if csig.published_at and sig.published_at:
            days_apart = abs((sig.published_at - csig.published_at).days)
        else:
            days_apart = None
        title_sim = _jaccard(sig.title_tokens, csig.title_tokens)
        if title_sim >= TITLE_SIMILARITY_THRESHOLD and (days_apart is None or days_apart <= TITLE_WINDOW_DAYS):
            matches.append(
                ClusterMatch(
                    cluster_id=cluster.id,
                    reason=f"제목 토큰 유사도 {title_sim:.2f}(약한 신호) — 검토 필요",
                    score=title_sim,
                    membership_type=IssueMembershipType.DUPLICATE_REPORT,
                )
            )
    return matches


def assign_document_to_cluster(
    db: Session, document: SourceDocument, *, actor_user_id=None
) -> IssueCluster:
    """문서 1건을 기존 클러스터에 합치거나, 필요하면 새 클러스터를 만든다.

    이미 어떤 클러스터에도 속해 있다면(unique 제약) 재배정하지 않고 그대로 반환한다.
    """
    existing_membership = (
        db.query(IssueClusterDocument).filter(IssueClusterDocument.document_id == document.id).one_or_none()
    )
    if existing_membership is not None:
        return db.get(IssueCluster, existing_membership.issue_cluster_id)

    classification = db.query(DocumentClassification).filter_by(document_id=document.id).one_or_none()
    field_code = classification.primary_field_code if classification else None
    if field_code is None:
        field_code = document.field_code  # 분류 보류 문서는 하위호환 필드로라도 분야를 둬야 클러스터를 만들 수 있다

    sig = build_signature(db, document)
    global_candidates = find_candidate_clusters_global(db)
    same_field_candidates = find_candidate_clusters_same_field(db, field_code)
    matches = match_document_to_clusters(sig, global_candidates, same_field_candidates)

    now = datetime.now(timezone.utc)

    if len(matches) >= 2:
        # 서로 다른 클러스터와 동시에 매칭 — 모호함. 자동 통합하지 않고 독립 클러스터로 검토 대기.
        cluster = IssueCluster(
            title=document.title,
            field_code=field_code,
            first_seen_at=document.published_at or now,
            representative_document_id=document.id,
            last_activity_at=document.published_at or now,
            review_status=ClusterReviewStatus.NEEDS_REVIEW,
            created_by_method=ClassificationMethod.RULE_BASED,
            summary=(
                f"자동 배정 보류 — {len(matches)}개 클러스터와 동시에 매칭되어 모호함"
                f"({'; '.join(m.reason for m in matches)})"
            ),
        )
        db.add(cluster)
        db.flush()
        _add_membership(db, cluster.id, document.id, IssueMembershipType.PRIMARY, None,
                         cluster.summary, ClassificationMethod.RULE_BASED, actor_user_id)
        return cluster

    if len(matches) == 1:
        match = matches[0]
        cluster = db.get(IssueCluster, match.cluster_id)
        cluster.last_activity_at = document.published_at or now
        if match.membership_type == IssueMembershipType.DUPLICATE_REPORT:
            cluster.review_status = ClusterReviewStatus.NEEDS_REVIEW

        # "허브" 문서 탐지: 매칭된 클러스터가 이번에 "매칭에 실제로 쓰인 식별자 종류"와 같은
        # 종류의 *다른* 값도 이미 갖고 있다면(예: 설명회 1건이 서로 다른 두 RIN을 함께 공지),
        # 서로 다른 조치를 묶고 있을 위험이 있다 — 검토 대기로 둔다.
        # 주의(실데이터에서 발견): RIN으로 매칭됐는데 Docket 번호가 다른 것은 정상이다 — 같은
        # 규제(RIN)라도 NPRM 단계와 Final Rule 단계에서 기관이 새 Docket 번호를 부여하는 경우가
        # 실제로 있었다(NHTSA-2024-0012 → NHTSA-2024-0091, 동일 RIN 2127-AM43). 그래서 매칭에
        # 쓰인 식별자 종류만 비교하고, 다른 종류의 식별자 차이는 허브 판단 근거로 쓰지 않는다.
        matched_csig = next(
            (csig for c, csig in global_candidates if c.id == match.cluster_id), None
        )
        if matched_csig is not None and match.membership_type == IssueMembershipType.FOLLOW_UP:
            matched_via_rin = "RIN" in match.reason
            other_ids = (matched_csig.rins - sig.rins) if matched_via_rin else (matched_csig.dockets - sig.dockets)
            if other_ids:
                cluster.review_status = ClusterReviewStatus.NEEDS_REVIEW
                id_label = "RIN" if matched_via_rin else "Docket"
                hub_note = (
                    f"허브 문서 가능성 — 이 클러스터에 현재 문서와 무관한 {id_label} 번호도 함께 묶여 있음"
                    f"(기타: {', '.join(sorted(other_ids))}). 서로 다른 조치가 섞였을 수 있어 검토 필요."
                )
                cluster.summary = f"{cluster.summary + ' / ' if cluster.summary else ''}{hub_note}"

        _add_membership(db, cluster.id, document.id, match.membership_type, match.score,
                         match.reason, ClassificationMethod.RULE_BASED, actor_user_id)
        db.flush()
        return cluster

    # 매칭 없음 — 새 독립 클러스터
    cluster = IssueCluster(
        title=document.title,
        field_code=field_code,
        first_seen_at=document.published_at or now,
        representative_document_id=document.id,
        last_activity_at=document.published_at or now,
        review_status=ClusterReviewStatus.CONFIRMED,  # 혼자뿐이라 통합 판단 자체가 없음 — 모호함 없음
        created_by_method=ClassificationMethod.RULE_BASED,
    )
    db.add(cluster)
    db.flush()
    _add_membership(db, cluster.id, document.id, IssueMembershipType.PRIMARY, None,
                     "신규 독립 이슈 — 기존 클러스터와 매칭되는 RIN/Docket/제목 유사도 없음",
                     ClassificationMethod.RULE_BASED, actor_user_id)
    return cluster


def _add_membership(db: Session, cluster_id, document_id, membership_type, score, reasoning, method, actor_user_id):
    db.add(
        IssueClusterDocument(
            issue_cluster_id=cluster_id, document_id=document_id, membership_type=membership_type,
            similarity_score=score, judgment_reasoning=reasoning, method=method,
        )
    )
    db.add(
        IssueClusterMembershipHistory(
            document_id=document_id, previous_issue_cluster_id=None, new_issue_cluster_id=cluster_id,
            action="assigned", changed_by_user_id=actor_user_id, reason=reasoning,
        )
    )
    db.flush()


def manual_merge_clusters(db: Session, *, source_cluster_id, target_cluster_id, user_id, reason: str | None) -> IssueCluster:
    """연구원이 두 클러스터를 수동 병합한다 — source의 모든 문서를 target으로 옮긴다."""
    members = db.query(IssueClusterDocument).filter(IssueClusterDocument.issue_cluster_id == source_cluster_id).all()
    for m in members:
        db.add(
            IssueClusterMembershipHistory(
                document_id=m.document_id, previous_issue_cluster_id=source_cluster_id,
                new_issue_cluster_id=target_cluster_id, action="merged", changed_by_user_id=user_id, reason=reason,
            )
        )
        m.issue_cluster_id = target_cluster_id
        m.method = ClassificationMethod.RESEARCHER
    target = db.get(IssueCluster, target_cluster_id)
    target.review_status = ClusterReviewStatus.CONFIRMED
    target.last_activity_at = datetime.now(timezone.utc)
    source = db.get(IssueCluster, source_cluster_id)
    source.status = "merged"
    db.flush()
    return target


def manual_split_document(db: Session, *, document_id, user_id, reason: str | None) -> IssueCluster:
    """연구원이 문서 1건을 현재 클러스터에서 분리해 새 독립 클러스터로 만든다."""
    membership = db.query(IssueClusterDocument).filter(IssueClusterDocument.document_id == document_id).one()
    old_cluster_id = membership.issue_cluster_id
    document = db.get(SourceDocument, document_id)
    classification = db.query(DocumentClassification).filter_by(document_id=document_id).one_or_none()
    field_code = classification.primary_field_code if classification else document.field_code

    now = datetime.now(timezone.utc)
    new_cluster = IssueCluster(
        title=document.title, field_code=field_code, first_seen_at=document.published_at or now,
        representative_document_id=document.id, last_activity_at=document.published_at or now,
        review_status=ClusterReviewStatus.CONFIRMED, created_by_method=ClassificationMethod.RESEARCHER,
        summary=f"연구원이 분리함: {reason or ''}",
    )
    db.add(new_cluster)
    db.flush()

    db.add(
        IssueClusterMembershipHistory(
            document_id=document_id, previous_issue_cluster_id=old_cluster_id,
            new_issue_cluster_id=new_cluster.id, action="split", changed_by_user_id=user_id, reason=reason,
        )
    )
    membership.issue_cluster_id = new_cluster.id
    membership.membership_type = IssueMembershipType.PRIMARY
    membership.method = ClassificationMethod.RESEARCHER
    membership.judgment_reasoning = f"연구원 수동 분리: {reason or ''}"
    db.flush()
    return new_cluster
