"""실제 AI 소규모 검증 계획서 생성 — API 키·비용 승인 전에는 호출하지 않고, DB의 공개 공식 원문으로 대상·예상 토큰·예상 비용만 계산한다.

실행: python -m app.make_ai_validation_plan docs/AI_VALIDATION_PLAN.md
"""

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models.candidate import Candidate
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.enums import ClassificationRelevance
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source_document import SourceDocument
from app.services import ai_analysis_service as svc
from app.services import ai_evidence
from app.services.ai_service import cost_usd

PRICE_NOTE = "claude-sonnet-5-5: 입력 $2 / 출력 $10 (USD/100만 토큰) — 공식 모델 문서·가격표(platform.claude.com) 2026-10-27 확인값. 실제 사용 전 관리자 단가표에서 다시 확인."
PRICE = (2.0, 10.0)
TEST_MARKERS = ("E2E", "e2e-", "[시범]", "[합성", "3-6", "CI Fixture")


def _cat(title: str, url: str, text: str) -> str:
    low = f"{title} {text[:800]}".lower()
    if "arxiv" in url:
        return "기술·연구 문서"
    if any(k in low for k in ("final rule", "proposed rule", "notice of", "petition", "docket", "rulemaking")):
        return "정책·규제 문서"
    return "기타 공개 문서"


def _facts(text: str, n: int = 4) -> str:
    dates = sorted(ai_evidence.extract_dates(text[:12000]))[:n]
    nums = sorted(ai_evidence.extract_numbers(text[:12000]), key=len, reverse=True)[:n]
    return f"날짜 {', '.join(dates) or '없음'} / 수치 {', '.join(nums) or '없음'}"


def build(db) -> str:
    docs = []
    for d, ft in db.execute(select(SourceDocument, DocumentFullText).join(DocumentFullText, DocumentFullText.document_id == SourceDocument.id)
                            .join(DocumentClassification, DocumentClassification.document_id == SourceDocument.id)
                            .where(DocumentClassification.relevance == ClassificationRelevance.MATCHED)).all():
        if any(m in d.title for m in TEST_MARKERS) or not d.origin_url or not ft.full_text:
            continue
        docs.append((d, ft))
    by_cat = defaultdict(list)
    for d, ft in docs:
        if len(ft.full_text) >= 1500:
            by_cat[_cat(d.title, d.origin_url, ft.full_text)].append((d, ft))
    picks: list[tuple[str, SourceDocument, DocumentFullText]] = []
    for cat, n in (("정책·규제 문서", 2), ("기술·연구 문서", 2)):
        for d, ft in sorted(by_cat[cat], key=lambda x: x[0].published_at or date.min, reverse=True)[:n]:
            picks.append((cat, d, ft))
    fmv = next(((d, ft) for d, ft in docs if "FMVSS" in d.title or "Electric Powertrain" in d.title), None)
    if fmv:
        picks.append(("후속 규정 사례(FMVSS 305a 시행일 변경)", *fmv))
    short = next(((d, ft) for d, ft in docs if 200 <= len(ft.full_text) < 1200), None)
    if short:
        picks.append(("근거 부족 사례(원문이 짧음)", *short))

    out = ["# AI 소규모 검증 계획서 (실제 호출 전 · 승인 대기)", "",
           f"작성일 {date.today().isoformat()} · **이 문서는 계획일 뿐이며 실제 유료 AI 호출은 하지 않았다.** API 키 설정과 비용 승인 후 별도 지시에 따라 실행한다.", "",
           "## 0. 전제", "", f"- 제공자/모델: Anthropic `claude-sonnet-5-5` (공식 모델 문서에 존재하는 ID). 단가: {PRICE_NOTE}",
           "- 비용 계산식: 입력 토큰 = 입력 문자 수 ÷ 2.5 + 지시문 900, 출력 토큰은 상한 가정 5,000(실제는 이보다 작을 수 있음), 비용 = 입력×단가 + 출력×단가. **추정치이며 제공자 청구금액이 아니다.**",
           "- 분석 대상은 DB에 저장된 공개 공식 원문(Federal Register·arXiv 등)만 사용하며 비공개 원고·개인정보는 보내지 않는다.",
           "- CI에서는 실제 호출을 하지 않는다. 실행은 사용자가 키를 설정하고 비용을 승인한 뒤 로컬 통합 사이트에서 수동으로 한다.", "",
           "## 1. 공식 원문 단위 분석 (5건 이상)", "",
           "| # | 구분 | 제목 | URL | 분석 목적 | 예상 입력/출력 토큰 | 예상 비용(USD) | 검증할 사실·날짜·수치 |", "|---|---|---|---|---|---|---|---|"]
    total_in = total_out = 0
    total_cost = 0.0
    for i, (cat, d, ft) in enumerate(picks, 1):
        est = svc.estimate(db, "document", d.id)
        c = cost_usd(PRICE, est["est_input_tokens"], est["est_output_tokens"]) or 0
        total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total_cost += c
        purpose = {"정책·규제 문서": "핵심 변화·일정·기관 입장 요약 정확성", "기술·연구 문서": "연구 기여·수치 요약, 보고서 활용 가능성",
                   "후속 규정 사례(FMVSS 305a 시행일 변경)": "발표일·시행일·준수 시한 구분", "근거 부족 사례(원문이 짧음)": "근거 부족 시 보류·'근거 없음' 표시"}.get(cat, "원문 요약")
        out.append(f"| {i} | {cat} | {d.title[:70]} | {d.origin_url} | {purpose} | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | {c} | {_facts(ft.full_text)} |")

    # 이슈
    multi = []
    for cl in db.scalars(select(IssueCluster)).all():
        n = db.scalar(select(func.count(IssueClusterDocument.id)).where(IssueClusterDocument.issue_cluster_id == cl.id)) or 0
        if n >= 2 and not any(m in cl.title for m in TEST_MARKERS):
            est = svc.estimate(db, "issue", cl.id)
            if len(est["documents"]) >= 2:
                multi.append((cl, est))
    multi.sort(key=lambda x: -len(x[1]["documents"]))
    out += ["", "## 2. 복수 원문 이슈 종합 분석 (2건 이상)", "", "| # | 이슈 | 원문 | 분석 목적 | 예상 입력/출력 | 예상 비용 | 검증할 사실 |", "|---|---|---|---|---|---|---|"]
    issue_rows = []
    for i, (cl, est) in enumerate(multi[:2], 1):
        c = cost_usd(PRICE, est["est_input_tokens"], est["est_output_tokens"]) or 0
        total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total_cost += c
        links = "<br>".join(f"{x['title'][:50]} ({x['published'] or '-'}) {x['url']}" for x in est["documents"])
        purpose = "논쟁이 없는 이슈에서 임의의 논쟁을 만들지 않는지, 발표일 순서·후속 변화 구분" if i == 1 else "복수 기관·국가 입장 비교 시 근거 2건 이상 규칙 준수"
        out.append(f"| {i} | {cl.title[:60]} | {links} | {purpose} | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | {c} | 문서별 발표일·시행일·수치 대조 |")
        issue_rows.append((cl, est))
    # 후보 제안 & 초안
    out += ["", "## 3. 후보주제 제안 (2건 이상)", "", "| # | 대상 이슈 | 기존 후보주제 | 분석 목적 | 예상 입력/출력 | 예상 비용 |", "|---|---|---|---|---|---|"]
    for i, (cl, est) in enumerate(issue_rows, 1):
        e2 = svc.estimate(db, "candidate", cl.id)
        c = cost_usd(PRICE, e2["est_input_tokens"], e2["est_output_tokens"]) or 0
        total_in += e2["est_input_tokens"]; total_out += e2["est_output_tokens"]; total_cost += c
        out.append(f"| {i} | {cl.title[:60]} | {len(e2['existing_candidate_ids'])}건(있으면 연결) | 선정 필요성·쟁점·국내 관련성의 근거 부족 표시, 임의 점수 미부여 | {e2['est_input_tokens']:,} / {e2['est_output_tokens']:,} | {c} |")
    out += ["", "## 4. 원고 초안 제안 (1건 이상)", "", "| # | 대상 후보주제 | 분석 목적 | 예상 입력/출력 | 예상 비용 |", "|---|---|---|---|---|"]
    cand = None
    for cl, _ in issue_rows:
        cand = db.scalar(select(Candidate).where(Candidate.issue_cluster_id == cl.id))
        if cand:
            break
    if cand:
        e3 = svc.estimate(db, "draft", cand.id)
        c = cost_usd(PRICE, e3["est_input_tokens"], e3["est_output_tokens"]) or 0
        total_in += e3["est_input_tokens"]; total_out += e3["est_output_tokens"]; total_cost += c
        out.append(f"| 1 | {cand.title[:70]} | 사실 문장 위주 초안의 근거 매핑률, 삽입 후 각주 미검증 상태 | {e3['est_input_tokens']:,} / {e3['est_output_tokens']:,} | {c} |")
    else:
        out.append("| 1 | (후보주제가 있는 이슈를 확보한 뒤 지정) | - | - | - |")
    out += ["", f"## 5. 합계(추정)", "", f"- 입력 약 {total_in:,} 토큰 · 출력 상한 약 {total_out:,} 토큰 · **예상 비용 약 ${round(total_cost, 2)}** (claude-sonnet-5-5 단가 기준, 상한 추정).", "- 다른 모델(예: claude-haiku-5-5, claude-opus-5-5)을 쓰면 단가표(관리자 설정)에 맞춰 같은 식으로 다시 계산한다.",
            "- 예상 소요 시간은 참고용: 요청당 수십 초~2분(원문 길이·출력량에 따라 다름).",
            "", "## 6. 정상 결과 판단 기준", "",
            "1. 사실(fact) 문장마다 원문 발췌문이 서버 대조에서 '원문 근거 확인'이고 날짜·수치가 발췌문과 일치한다.",
            "2. '의미 불일치 가능성'(날짜 역할·단위·부등호·부정)이 연구원 검토에서 오탐 또는 정정 가능한 수준이다.",
            "3. 단일 원문으로 국가 비교·논쟁을 만들지 않고, 근거가 없는 항목은 '근거 부족'으로 비워 둔다.",
            "4. 후속 규정 사례에서 이미 변경된 시행일을 현재 사실로 쓰지 않는다.",
            "5. 후보주제 제안이 국내 산업 관련성에 임의 점수를 붙이지 않는다.",
            "", "## 7. 오류 판정 기준(검증 실패로 집계)", "",
            "- 원문에 없는 발췌문(검증 실패), 값이 다른 문장(근거 불일치), 엉뚱한 문서에 연결된 근거, 사실 문장인데 근거 없음.",
            "- 시행일·발표일·준수 시한을 혼동한 문장, 단위·부등호·부정이 뒤집힌 문장, 원문에 없는 논쟁·국가 입장, 국내 산업 영향 과장.",
            "- 지표: 사실 문장 중 '근거 없음·불일치·검증 실패' 비율, 연구원이 정정한 문장 수, 과장·오류 사례 목록. **정확도를 100%라고 주장하지 않는다.**",
            "", "## 8. 실행 순서(승인 후)", "",
            "1. 서버 환경변수 `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`(필요 시 `AI_MODEL`) 설정 → 설정 화면 '연결 진단'으로 모델 사용 가능 확인(토큰 미사용).",
            "2. 관리자 단가표 확인 → 위 대상 순서대로 한 건씩 실행(실행 전 예상 비용 확인 창에서 확인).",
            "3. 결과를 원문과 대조해 오류 판정 기준에 따라 집계하고 보고한다."]
    return "\n".join(out) + "\n"


def main() -> None:
    db = SessionLocal()
    try:
        text = build(db)
    finally:
        db.close()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "AI_VALIDATION_PLAN.md")
    out.write_text(text, encoding="utf-8")
    print(f"검증 계획서 생성 → {out}")


if __name__ == "__main__":
    main()
