"""이슈 클러스터 단위 핵심내용·쟁점·국가비교·국내시사점·논쟁 분석.

규칙 기반(AI 미설정) 모드의 원칙: 원문에서 직접 확인 가능한 것만 채우고, 해석·추정이 필요한
항목(쟁점 카테고리화, 국내 산업 연관성, 찬반 논쟁)은 신뢰할 만한 직접 근거가 없으면 비워 두거나
"평가 보류/추가 분석 필요"로 명시한다 — 원문에 없는 내용을 사실처럼 만들어내지 않기 위함이다.
"""

import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ai_analysis_run import AIAnalysisRun
from app.models.document_full_text import DocumentFullText
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.enums import ClassificationMethod, DisputeAnalysisStatus, VerificationStatus
from app.models.issue_analysis import IssueAnalysis
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.issue_dispute_point import IssueDisputePoint
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.ai_service import AIServiceError, extract_json_object, get_ai_provider

DISPUTE_SIGNAL_PATTERNS = [
    "however, industry", "industry groups argue", "critics say", "critics argue", "opposed",
    "raised concerns", "pushed back", "disagree", "반대", "우려를 표명", "이의를 제기", "이견",
]


def _member_documents(db: Session, cluster_id) -> list[SourceDocument]:
    members = db.query(IssueClusterDocument).filter(IssueClusterDocument.issue_cluster_id == cluster_id).all()
    docs = [db.get(SourceDocument, m.document_id) for m in members]
    docs.sort(key=lambda d: d.published_at or datetime.min.replace(tzinfo=timezone.utc))
    return docs


def _best_structured_extract(db: Session, docs: list[SourceDocument]) -> DocumentStructuredExtract | None:
    best = None
    best_len = -1
    for doc in docs:
        se = db.query(DocumentStructuredExtract).filter_by(document_id=doc.id).one_or_none()
        if se and se.key_content and len(se.key_content) > best_len:
            best = se
            best_len = len(se.key_content)
    return best


def _merge_json_lists(db: Session, docs: list[SourceDocument], field_name: str, limit: int = 12) -> list:
    merged = []
    for doc in docs:
        se = db.query(DocumentStructuredExtract).filter_by(document_id=doc.id).one_or_none()
        if not se:
            continue
        raw = getattr(se, field_name, None)
        if not raw:
            continue
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            continue
        merged.extend(items)
        if len(merged) >= limit:
            break
    return merged[:limit]


def _find_dispute_signal(lower_text: str, pattern: str) -> int | None:
    """pattern의 모든 출현 위치를 보되, "as opposed to"처럼 분쟁과 무관한 관용구는 건너뛴다
    (실데이터 검증에서 발견: "opposed" 단독 매칭의 상당수가 'A as opposed to B' 비교 관용구였음)."""
    start = 0
    while True:
        idx = lower_text.find(pattern, start)
        if idx == -1:
            return None
        if pattern == "opposed":
            preceding = lower_text[max(0, idx - 4) : idx].strip()
            following = lower_text[idx + len(pattern) : idx + len(pattern) + 4].strip()
            if preceding.endswith("as") or following.startswith("to"):
                start = idx + len(pattern)
                continue
        return idx


def _detect_disputes_rule_based(docs: list[SourceDocument], full_texts: dict) -> list[dict]:
    disputes = []
    for doc in docs:
        text = full_texts.get(doc.id, "") or ""
        lower = text.lower()
        for pattern in DISPUTE_SIGNAL_PATTERNS:
            idx = _find_dispute_signal(lower, pattern)
            if idx is not None:
                context = text[max(0, idx - 100) : idx + 200].replace("\n", " ")
                disputes.append({"document_id": doc.id, "quote": context, "pattern": pattern})
                break
    return disputes


def analyze_cluster_rule_based(db: Session, cluster: IssueCluster) -> dict:
    docs = _member_documents(db, cluster.id)
    full_texts = {}
    for doc in docs:
        ft = db.query(DocumentFullText).filter_by(document_id=doc.id).one_or_none()
        full_texts[doc.id] = ft.full_text if ft and ft.full_text else (doc.raw_text or "")

    best_se = _best_structured_extract(db, docs)
    key_summary = best_se.key_content if best_se else None
    background_purpose = best_se.background_purpose if best_se else None
    policy_tech_change = best_se.policy_tech_change if best_se else None
    key_figures = _merge_json_lists(db, docs, "key_figures_json")

    # 국가별 비교 — 실제로 확인되는 국가(출처 country_code)만 담는다. 데이터가 미국 중심이면
    # 그 사실 자체를 정직하게 남긴다(다른 나라 입장을 임의로 만들어내지 않는다).
    countries_seen = {}
    for doc in docs:
        source = db.get(Source, doc.source_id)
        if source and source.country_code:
            countries_seen.setdefault(source.country_code, []).append(doc.id)
    country_positions = [
        {
            "country_or_org": country,
            "position_summary": f"{country} 소재 {len(doc_ids)}건의 문서에서 확인됨(요약은 개별 문서 참고)",
            "source_document_id": str(doc_ids[0]),
        }
        for country, doc_ids in countries_seen.items()
    ]
    if len(countries_seen) <= 1:
        country_positions.append(
            {
                "country_or_org": None,
                "position_summary": (
                    "비교할 복수 국가의 자료가 수집되지 않음 — 현재 출처가 "
                    f"{list(countries_seen.keys())[0] if countries_seen else '미상'} 중심이라 "
                    "타국 입장을 임의로 작성하지 않음(추가 출처 확보 필요)"
                ),
                "source_document_id": None,
            }
        )

    disputes_raw = _detect_disputes_rule_based(docs, full_texts)
    dispute_status = DisputeAnalysisStatus.DISPUTES_FOUND if disputes_raw else DisputeAnalysisStatus.NO_DISPUTES_CONFIRMED

    return {
        "key_summary": key_summary,
        "background_purpose": background_purpose,
        "policy_tech_change": policy_tech_change,
        "key_figures": key_figures,
        "technical_issues": [],
        "policy_issues": [],
        "industry_concerns": [],
        "unconfirmed_points": [
            "규칙 기반(AI 미설정) 모드 — 기술적/정책적 쟁점 카테고리화는 해석이 필요해 생성하지 않음"
        ],
        "country_positions": country_positions,
        "domestic_industry_relevance": None,
        "domestic_rnd_impact": None,
        "domestic_policy_considerations": None,
        "domestic_monitoring_points": None,
        "domestic_has_sufficient_basis": False,
        "dispute_status": dispute_status,
        "disputes_raw": disputes_raw,
        "source_citations": {"key_summary": "대표 문서의 구조화 추출(key_content)에서 그대로 사용"},
    }


def _build_ai_prompt(cluster: IssueCluster, docs: list[SourceDocument], full_texts: dict) -> tuple[str, str]:
    system_prompt = (
        "당신은 ICT 주간기술동향 보고서 작성을 돕는 분석 보조원입니다. 주어진 이슈 클러스터에 속한 "
        "문서들만 근거로 핵심 이슈·쟁점·국가비교·국내산업 시사점을 분석하십시오. 원문에 없는 사실을 "
        "추정해 만들어내지 마십시오. 실제 논쟁이 확인되지 않으면 없다고 답하십시오. 국가별 자료가 "
        "없으면 해당 국가 입장을 임의로 만들지 마십시오. 반드시 JSON으로만 답하십시오."
    )
    docs_text = "\n\n---\n\n".join(
        f"[문서 {i+1}] {d.title}\n{(full_texts.get(d.id) or '')[:4000]}" for i, d in enumerate(docs[:5])
    )
    user_prompt = f"[이슈 클러스터 제목]\n{cluster.title}\n\n[소속 문서 {len(docs)}건 중 최대 5건]\n{docs_text}"
    return system_prompt, user_prompt


def analyze_cluster_with_ai(db: Session, cluster: IssueCluster, docs, full_texts) -> dict | None:
    provider = get_ai_provider()
    started = datetime.now(timezone.utc)
    if provider is None:
        db.add(
            AIAnalysisRun(
                document_id=docs[0].id, task_type="issue_analysis", provider=None, model=None,
                analysis_version="ai-v1", status="skipped_no_api_key", started_at=started, finished_at=started,
            )
        )
        return None
    system_prompt, user_prompt = _build_ai_prompt(cluster, docs, full_texts)
    run = AIAnalysisRun(
        document_id=docs[0].id, task_type="issue_analysis", provider=provider.name, model=provider.model,
        analysis_version="ai-v1", status="failed", started_at=started,
    )
    db.add(run)
    try:
        result = provider.complete_json(system_prompt, user_prompt)
        parsed = extract_json_object(result.text)
        run.status = "success"
        return parsed
    except AIServiceError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        return None
    finally:
        run.finished_at = datetime.now(timezone.utc)


def run_issue_analysis(db: Session, cluster: IssueCluster, *, prefer_ai: bool = True) -> IssueAnalysis:
    docs = _member_documents(db, cluster.id)
    full_texts = {}
    for doc in docs:
        ft = db.query(DocumentFullText).filter_by(document_id=doc.id).one_or_none()
        full_texts[doc.id] = ft.full_text if ft and ft.full_text else (doc.raw_text or "")

    generated_by = ClassificationMethod.RULE_BASED
    result = None
    if prefer_ai:
        result = analyze_cluster_with_ai(db, cluster, docs, full_texts)
        if result is not None:
            generated_by = ClassificationMethod.AI
    if result is None:
        result = analyze_cluster_rule_based(db, cluster)
        generated_by = ClassificationMethod.RULE_BASED

    existing = db.query(IssueAnalysis).filter_by(issue_cluster_id=cluster.id).one_or_none()
    if existing is None:
        existing = IssueAnalysis(issue_cluster_id=cluster.id)
        db.add(existing)

    existing.key_summary = result.get("key_summary")
    existing.background_purpose = result.get("background_purpose")
    existing.policy_tech_change = result.get("policy_tech_change")
    existing.key_figures_json = json.dumps(result.get("key_figures") or [], ensure_ascii=False)
    existing.technical_issues_json = json.dumps(result.get("technical_issues") or [], ensure_ascii=False)
    existing.policy_issues_json = json.dumps(result.get("policy_issues") or [], ensure_ascii=False)
    existing.industry_concerns_json = json.dumps(result.get("industry_concerns") or [], ensure_ascii=False)
    existing.unconfirmed_points_json = json.dumps(result.get("unconfirmed_points") or [], ensure_ascii=False)
    existing.country_positions_json = json.dumps(result.get("country_positions") or [], ensure_ascii=False)
    existing.domestic_industry_relevance = result.get("domestic_industry_relevance")
    existing.domestic_rnd_impact = result.get("domestic_rnd_impact")
    existing.domestic_policy_considerations = result.get("domestic_policy_considerations")
    existing.domestic_monitoring_points = result.get("domestic_monitoring_points")
    existing.domestic_has_sufficient_basis = bool(result.get("domestic_has_sufficient_basis", False))
    existing.dispute_status = result.get("dispute_status", DisputeAnalysisStatus.NOT_ANALYZED)
    existing.source_citations_json = json.dumps(result.get("source_citations") or {}, ensure_ascii=False)
    existing.verification_status = VerificationStatus.UNVERIFIED
    existing.generated_by = generated_by
    db.flush()

    # 규칙 기반 논쟁 탐지 결과를 IssueDisputePoint 행으로 변환(아주 보수적 — 강한 신호가 있을 때만).
    # 재분석 시 이전에 감지됐던 행이 이번엔 사라질 수 있으므로(예: 오탐 패턴 수정), 새 결과가
    # 비어 있어도 항상 먼저 지우고 다시 채운다 — 그래야 dispute_status와 실제 행이 어긋나지 않는다.
    if generated_by == ClassificationMethod.RULE_BASED:
        db.query(IssueDisputePoint).filter(IssueDisputePoint.issue_cluster_id == cluster.id).delete()
        for d in result.get("disputes_raw") or []:
            db.add(
                IssueDisputePoint(
                    issue_cluster_id=cluster.id,
                    dispute_title=f"'{d['pattern']}' 패턴 감지 — 연구원 확인 필요",
                    claim_a_text=d["quote"],
                    claim_a_source_document_id=d["document_id"],
                    claim_b_text="(규칙 기반 탐지는 한쪽 주장만 식별 가능 — 상대측 주장은 연구원이 직접 확인 필요)",
                    claim_b_source_document_id=None,
                    method=ClassificationMethod.RULE_BASED,
                )
            )
        db.flush()

    return existing
