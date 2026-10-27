"""실제 AI 소규모 검증 계획서 생성 — API 키·비용 승인 전에는 호출하지 않는다. DB의 공개 공식 원문으로 대상·예상 토큰·예상 비용만 계산하고,
각 원문의 URL 접근 가능 여부(공개 웹 GET)와 연방관보 메타데이터(발표일·시행일·정정·후속 여부)를 확인한다.

총수량을 맞추려고 무관한 원문을 넣지 않는다 — 대상은 ICT 9대 분야와 관련된 정책·규제·기술연구·후속 규정 자료에서 직접 고른다(CURATED).
실행: python -m app.make_ai_validation_plan docs/AI_VALIDATION_PLAN.md
"""

import sys
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source_document import SourceDocument
from app.services import ai_analysis_service as svc
from app.services import ai_evidence
from app.services.ai_service import cost_usd

PRICE = (2.0, 10.0)
PRICE_NOTE = "claude-sonnet-5-5: 입력 $2 / 출력 $10 (USD/100만 토큰) — 공식 모델 문서·가격표(platform.claude.com) 2026-10-27 확인값. 실제 사용 전 관리자 단가표에서 다시 확인."
FR_API = "https://www.federalregister.gov/api/v1/documents"

# (구분, 원문 URL에 포함된 문자열 또는 제목 일부, 분석 목적, 선정 이유)
CURATED_DOCS = [
    ("정책·규제 — 통신·주파수", "upper-c-band", "핵심 변경·일정·기관 입장 요약 정확성", "FCC의 3.7–4.2 GHz 대역 유연 사용 규제 — 실제 ICT(통신) 정책자료·공식 1차 출처·짧은 원문, **첫 실호출 대상**"),
    ("정책·규제 — 사이버보안", "request-for-information-rfi-on-modernizing-the-national-vulnerability", "RFI의 질의 항목·마감일·대상 구분", "NIST 취약점 데이터베이스 현대화 RFI — 보안 정책 자료"),
    ("정책·규제 — 반도체 수출통제", "foreign-produced-direct-product-rule-additions", "복잡한 규정의 적용 대상·시행일·예외 구분(원문 앞 12,000자 한도 확인)", "BIS 첨단 컴퓨팅·반도체 제조 장비 수출통제 — 반도체 정책 핵심 문서(원문이 매우 길어 절단 표시 검증 포함)"),
    ("기술·연구 — AI", "Ask to Distill", "연구 기여·수치 요약, 보고서 활용 가능성", "활용가치 '우선' 판정을 받은 AI 연구 논문"),
    ("기술·연구 — AI 보안", "PROVISO", "연구 방법·결과 수치 요약, 과장 여부", "LLM 에이전트 보안 연구 논문"),
    ("후속 규정 — FMVSS 305a 시행일 연기", "2025-02582", "발표일·시행일·준수 시한 구분, 후속 규정이 바꾼 것과 바꾸지 않은 것 구분", "2024-28707 최종 규정의 시행일을 2025.3.20.으로 연기한 공식 후속 규정(분량 작음)"),
]
HOLD_DOC = ("근거 부족 — 원문 전문 없음", "launches-centers-ai-manufacturing", "원문 전문이 없을 때 호출 없이 '분석 보류'(비용 0)가 되는지", "AI 관련 NIST 보도자료이나 전문 추출이 이루어지지 않은 실제 사례 — 호출 비용이 들지 않는 안전 검증")


def _find_doc(db, key: str) -> SourceDocument | None:
    rows = db.scalars(select(SourceDocument).where(SourceDocument.origin_url.ilike(f"%{key}%") | SourceDocument.title.ilike(f"%{key}%"))).all()
    return rows[0] if rows else None


def _reach(url: str) -> str:
    try:
        r = httpx.get(url, timeout=25, follow_redirects=True, headers={"User-Agent": "TNP-AI-Platform-plan-check/1.0"})
        return f"HTTP {r.status_code}" + ("" if r.status_code == 200 else " (접속 제한·확인 필요)")
    except httpx.HTTPError as exc:
        return f"확인 불가({exc.__class__.__name__}) — 일시 오류일 수 있음"


def _fr_meta(url: str) -> str:
    if "federalregister.gov" not in url:
        return "연방관보 아님"
    num = url.rstrip("/").split("/")[-2] if "/documents/" in url else None
    try:
        d = httpx.get(f"{FR_API}/{num}.json", timeout=25).json()
        bits = [f"유형 {d.get('type')}", f"발표 {d.get('publication_date')}"]
        if d.get("effective_on"):
            bits.append(f"시행 {d['effective_on']}")
        if d.get("correction_of"):
            bits.append("정정 문서")
        if d.get("corrections"):
            bits.append(f"정정 있음({len(d['corrections'])}건)")
        return " · ".join(bits)
    except Exception:  # noqa: BLE001 — 계획서 생성 중 네트워크 오류는 표시만 한다
        return "메타데이터 조회 실패"


def _facts(text: str, n: int = 4) -> str:
    head = text[:svc.MAX_CHARS_PER_DOC]
    dates = sorted(ai_evidence.extract_dates(head))[:n]
    nums = sorted(ai_evidence.extract_numbers(head), key=len, reverse=True)[:n]
    return f"날짜 {', '.join(dates) or '없음'} / 수치 {', '.join(nums) or '없음'}"


def _row(db, d: SourceDocument):
    ft = db.scalar(select(DocumentFullText).where(DocumentFullText.document_id == d.id))
    cl = db.scalar(select(DocumentClassification).where(DocumentClassification.document_id == d.id))
    va = db.scalar(select(DocumentValueAssessment).where(DocumentValueAssessment.document_id == d.id))
    return ft, (cl.primary_field_code.value if cl and cl.primary_field_code else "-"), (va.rating.value if va else "-")


def _c(est) -> float:
    return cost_usd(PRICE, est["est_input_tokens"], est["est_output_tokens"]) or 0.0


def build(db) -> str:
    out = ["# AI 소규모 검증 계획서 (실제 호출 전 · 승인 대기)", "",
           f"작성일 {date.today().isoformat()} · **이 문서는 계획일 뿐이며 실제 유료 AI 호출은 하지 않았다.** API 키 설정과 사용자의 검증·비용 승인 후 별도 지시로만 실행한다.", "",
           "## 0. 전제", "",
           f"- 제공자/모델: Anthropic `claude-sonnet-5-5`(공식 모델 문서에 존재). 단가: {PRICE_NOTE}",
           "- 비용 계산식: 입력 토큰 = 입력 문자 수 ÷ 2.5 + 지시문 900, 출력 토큰은 상한 가정 5,000, 비용 = 입력×단가 + 출력×단가. **추정치이며 제공자 청구금액이 아니다.** Sonnet 5.5는 적응형 사고가 기본이라 사고 토큰도 출력 토큰으로 과금되므로 실제 출력이 가정보다 클 수 있다(출력 한도 12,000토큰 이내).",
           f"- 원문은 호출당 문서 {svc.MAX_DOCS}건·문서당 앞 {svc.MAX_CHARS_PER_DOC:,}자까지만 보낸다(그 이상은 '일부만 분석'으로 표시). 매우 긴 규정의 뒷부분 내용은 이번 검증 범위가 아니다.",
           "- 분석 대상은 DB에 저장된 공개 공식 원문만 사용하며 비공개 원고·개인정보는 보내지 않는다. 총수량을 맞추려고 무관한 행정공고(라디오·TV 방송국 허가, 정보수집 승인 요청, 정정 공고 등)는 넣지 않았다.",
           "- 안전장치: 실제 호출은 관리자 1건 승인(대상·모델·예산 상한 지정, 1회용)이 있어야 하고, 예상 비용이 상한을 넘으면 호출 전에 차단되며, 자동 재시도·나머지 문서 자동 분석은 없다.", "",
           "## 1. 공식 원문 단위 분석", "",
           "| # | 구분 | 제목 | URL / 접근 | ICT 분야·활용가치 | 발표일·시행·정정 | 원문 확보 | 분석 목적 | 선정 이유 | 예상 입력/출력 토큰 | 예상 비용 | 검증할 사실·날짜·수치 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    total_in = total_out = 0
    total = 0.0
    first_call = None
    for i, (cat, key, purpose, why) in enumerate(CURATED_DOCS, 1):
        d = _find_doc(db, key)
        if d is None:
            out.append(f"| {i} | {cat} | (DB에 없음: {key}) | - | - | - | - | {purpose} | {why} | - | - | - |")
            continue
        ft, field, rating = _row(db, d)
        est = svc.estimate(db, "document", d.id)
        c = _c(est)
        total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total += c
        if first_call is None and "upper-c-band" in d.origin_url:
            first_call = (d, est, c)
        out.append(f"| {i} | {cat} | {d.title[:70]} | {d.origin_url} ({_reach(d.origin_url)}) | {field} · {rating} | {d.published_at.date() if d.published_at else '-'} · {_fr_meta(d.origin_url)} | {len(ft.full_text):,}자(보냄 {est['documents'][0]['chars']:,}자) | {purpose} | {why} | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | ${c} | {_facts(ft.full_text)} |")
    hd = _find_doc(db, HOLD_DOC[1])
    if hd is not None:
        ft, field, rating = _row(db, hd)
        out.append(f"| {len(CURATED_DOCS) + 1} | {HOLD_DOC[0]} | {hd.title[:70]} | {hd.origin_url} ({_reach(hd.origin_url)}) | {field} · {rating} | {hd.published_at.date() if hd.published_at else '-'} | 없음(분석 보류 대상) | {HOLD_DOC[2]} | {HOLD_DOC[3]} | 호출 안 함 | $0 | 보류 메시지·근거 부족 표시 |")

    # FMVSS 시나리오
    nums = {"2024-28707": None, "2025-02582": None, "2026-11072": None}
    for k in nums:
        nums[k] = _find_doc(db, k)
    cluster_id = None
    if nums["2024-28707"]:
        cluster_id = db.scalar(select(IssueClusterDocument.issue_cluster_id).where(IssueClusterDocument.document_id == nums["2024-28707"].id))
    out += ["", "## 2. FMVSS 305a 후속 규정 비교 시나리오 (복수 원문 이슈 #1)", "",
            "같은 이슈를 입력 문서 범위만 바꿔 세 번 분석해, AI가 기존 규정만 인용할 때와 후속 규정까지 반영할 때를 비교한다.", "",
            "| 시나리오 | 입력 문서 | 기대(정상) 결과 | 오류 판정 | 예상 입력/출력 | 예상 비용 |", "|---|---|---|---|---|---|"]
    fm_cost = 0.0
    scen = [("S1 기존 규정만", ["2024-28707"], "시행일 2025-02-18, 준수 시한 2025-12-22(비상대응 문서화)·2027-09-01(4,536 kg 이하)·2028-09-01(초과)을 구분해 서술하되 '후속 변경 여부 확인 필요'(gap)를 남긴다", "후속 문서 없이 '시행일이 연기되었다'고 단정하면 오류(원문 근거 없음)"),
            ("S2 후속 규정 포함", ["2024-28707", "2025-02582"], "시행일은 2025-03-20으로 연기됨을 근거와 함께 쓰고, 2025-02-18을 현재 사실로 쓰지 않는다. 준수 시한은 후속 문서가 바꾼다고 하지 않았음을 구분", "2025-02-18을 현재 시행일로 서술, 준수 시한을 연기된 것으로 서술하면 오류"),
            ("S3 이후 개정 포함", ["2024-28707", "2025-02582", "2026-11072"], "2026-06-03 규정(2026-07-06 시행)은 별도 규칙의 일부로 305a S9.3 문구만 개정했음(요건 변경 없음)을 구분하고, 'mandatory applicability begins on September 1, 2027'을 시행일과 혼동하지 않는다", "개정 규정의 시행일(2026-07-06)을 305a 시행·준수일로 혼동하면 오류")]
    for name, ids, expect, bad in scen:
        sel = [nums[i].id for i in ids if nums[i]]
        if cluster_id and len(sel) == len(ids):
            est = svc.estimate(db, "issue", cluster_id, sel)
            c = _c(est)
            fm_cost += c; total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total += c
            links = "<br>".join(f"{x['title'][:40]} {x['published']} {x['url']}" for x in est["documents"])
            out.append(f"| {name} | {links} | {expect} | {bad} | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | ${c} |")
        else:
            out.append(f"| {name} | (문서가 DB의 같은 이슈에 없음) | {expect} | {bad} | - | - |")
    out += ["", "- 관련 사실(공식 원문 확인): 2024-28707(2024-12-20) 최종 규정 — 시행일 2025-02-18, 준수 시한 2025-12-22(비상대응 문서화)·2027-09-01(GVWR 4,536 kg 이하)·2028-09-01(초과). 2025-02582(2025-02-14) — 시행일을 2025-03-20까지 연기(준수 시한 변경은 언급 없음). 2026-11072(2026-06-03, 시행 2026-07-06) — FMVSS 214 정리 규칙의 일부로 305a S9.3 참조 문구 개정, 요건 변경 없음.",
            "- Federal Register에서 2025-02582 이후 같은 문서번호 체계(Docket NHTSA-2024-0091)의 추가 후속 문서는 확인되지 않았고, 2026-11072만 305a를 개정한다(2026-10-27 조회)."]

    # 이슈 #2
    gr = db.scalar(select(SourceDocument).where(SourceDocument.title.ilike("%Group Registration of Updates to a News Website%")))
    gr_cluster = db.scalar(select(IssueClusterDocument.issue_cluster_id).where(IssueClusterDocument.document_id == gr.id)) if gr else None
    out += ["", "## 3. 복수 원문 이슈 #2 — 논쟁이 없는 이슈", ""]
    if gr_cluster:
        est = svc.estimate(db, "issue", gr_cluster)
        c = _c(est)
        total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total += c
        links = "<br>".join(f"{x['title'][:50]} {x['published']} {x['url']}" for x in est["documents"])
        out += ["| 이슈 | 원문 | 분석 목적 | 예상 입력/출력 | 예상 비용 | 검증할 사실 |", "|---|---|---|---|---|---|",
                f"| Group Registration of Updates to a News Website (저작권청, 콘텐츠·미디어) | {links} | 제안 규칙과 후속 문서의 변경점만 정리하고 **임의의 논쟁·국가별 입장을 만들지 않는지**, 발표일 순서 구분 | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | ${c} | 문서별 발표일·마감일·조항 수치 대조 |"]
    # 후보·초안
    out += ["", "## 4. 후보주제 제안 (2건)", "", "| # | 대상 이슈 | 기존 후보 | 분석 목적 | 예상 입력/출력 | 예상 비용 |", "|---|---|---|---|---|---|"]
    for i, (name, cid) in enumerate([("FMVSS 305a(S2 범위: 2024-28707 + 2025-02582)", cluster_id), ("Group Registration of Updates to a News Website", gr_cluster)], 1):
        if not cid:
            continue
        sel = [nums["2024-28707"].id, nums["2025-02582"].id] if i == 1 and nums["2024-28707"] and nums["2025-02582"] else None
        est = svc.estimate(db, "candidate", cid, sel)
        c = _c(est)
        total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total += c
        out.append(f"| {i} | {name} | {len(est['existing_candidate_ids'])}건(있으면 연결) | 선정 필요성·쟁점·국내 관련성의 '근거 부족' 표시, 임의 점수 미부여 | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | ${c} |")
    out += ["", "## 5. 원고 초안 제안 (1건)", "", "| 대상 후보주제 | 입력 범위 | 분석 목적 | 예상 입력/출력 | 예상 비용 |", "|---|---|---|---|---|"]
    from app.models.candidate import Candidate

    cand = db.scalar(select(Candidate).where(Candidate.issue_cluster_id == cluster_id)) if cluster_id else None
    if cand and nums["2024-28707"] and nums["2025-02582"]:
        est = svc.estimate(db, "draft", cand.id, [nums["2024-28707"].id, nums["2025-02582"].id])
        c = _c(est)
        total_in += est["est_input_tokens"]; total_out += est["est_output_tokens"]; total += c
        out.append(f"| {cand.title[:70]} | 2024-28707 + 2025-02582 | 시행일 연기를 반영한 사실 문장 초안의 근거 매핑률, 삽입 후 각주 미검증 상태, 원문 변경 재검토 연계 | {est['est_input_tokens']:,} / {est['est_output_tokens']:,} | ${c} |")
    out += ["", "## 6. 비용 합계(추정·상한)", "",
            f"- 전체 계획: 입력 약 {total_in:,} 토큰 · 출력 상한 약 {total_out:,} 토큰 · **예상 비용 약 ${round(total, 2)}** (claude-sonnet-5-5 단가 기준).",
            (f"- **최초 실호출 1건(권장)**: {first_call[0].title[:60]} ({first_call[0].origin_url}) — 예상 입력 {first_call[1]['est_input_tokens']:,} / 출력 상한 {first_call[1]['est_output_tokens']:,} 토큰, **예상 비용 약 ${first_call[2]}**. 최대 계산 비용(출력 12,000토큰 가정)과 권장 승인 상한은 사전 점검 화면에서 확인한다(제안: 첫 호출 상한 $0.15 이내)." if first_call else "- 최초 실호출 1건: 2025-02582를 DB에 추가한 뒤 지정한다."),
            "- 요청별 상한: 관리자 승인마다 예산 상한을 지정하고, 전역 상한(`AI_MAX_COST_PER_REQUEST_USD`)을 둘 수 있다. 예상 비용이 상한을 넘으면 호출 전에 차단된다.",
            "- 예상 소요 시간(참고): 요청당 수십 초~2분. 다른 모델을 쓰면 단가표에 맞춰 다시 계산한다.", "",
            "## 7. 품질 평가(실제 호출 후 연구원이 7개 항목으로 평가)", "",
            "① 원문 핵심 내용 요약 정확성 ② 날짜·수치·단위·적용대상 정확성 ③ 기존 정책과 후속 변경 구분 ④ 모든 핵심 사실의 원문 근거 ⑤ 원문에 없는 논쟁·국가별 입장 생성 여부 ⑥ 국내 산업 영향·추가 검토 사항 구분 ⑦ 보고서 원고 활용 가능성.",
            "- 평가는 분석 화면의 '품질 평가'에 저장되며, **모의 응답 평가와 실제 AI 평가는 합산하지 않고** 설정 화면에서 따로 집계된다.",
            "- 함께 기록: 의미 불일치 사례(날짜 역할·단위·부등호·부정), 근거 부족 사례, 잘못된 출처 연결 사례, 사실 문장 중 근거 없음·불일치·검증 실패 비율. **정확도를 100%라고 주장하지 않는다.**",
            "", "### 정상 결과 기준", "",
            "1. 사실 문장마다 원문 발췌문이 서버 대조에서 '원문 근거 확인'이고 날짜·수치가 발췌문과 일치한다.", "2. '의미 불일치 가능성' 표시가 연구원 검토에서 오탐이거나 정정 가능한 수준이다.",
            "3. 단일 원문으로 국가 비교·논쟁을 만들지 않고 근거가 없는 항목은 비워 '근거 부족'으로 둔다.", "4. 후속 규정 시나리오에서 이미 변경된 시행일을 현재 사실로 쓰지 않는다.", "5. 후보주제 제안이 국내 산업 관련성에 임의 점수를 붙이지 않는다.",
            "", "### 오류 판정 기준", "",
            "- 원문에 없는 발췌문(검증 실패), 값이 다른 문장(근거 불일치), 엉뚱한 문서에 연결된 근거, 사실 문장인데 근거 없음.",
            "- 시행일·발표일·준수 시한 혼동, 단위·부등호·부정 반전, 원문에 없는 논쟁·국가 입장, 국내 산업 영향 과장.", "",
            "## 8. 실행 순서(승인 후 · 한 번에 한 건)", "",
            "1. 서버 환경변수 설정(`docs/AI_SETUP.md`) → 설정 화면 '연결 진단'(모델 목록 조회, 토큰 미사용)으로 모델 사용 가능 확인.",
            "2. 사용자 검증·비용 승인 → 관리자가 위 '최초 실호출 1건'을 화면에서 1건 승인(예산 상한 지정) → 실행 → 실제 토큰·계산 비용·오류 보고(제공자 청구금액과 구분).",
            "3. 결과를 원문과 대조해 품질 평가 저장 → 이상이 없으면 사용자가 다음 대상을 다시 승인(자동으로 나머지 문서를 분석하지 않는다).", "",
            "## 9. 이번 점검에서 확인한 한계", "",
            "- BIS 수출통제 규정처럼 매우 긴 원문은 앞 12,000자만 분석되므로 뒤쪽 조항의 정확성은 이번 검증 범위가 아니다(화면에 '일부만 분석' 표시).",
            "- ICT 관련성 주의: FMVSS 305a는 사용자가 지정한 후속 규정 처리 검증 시나리오다. 전기차 동력계 안전기준이라 ICT 9대 분야(SW·자율주행 등)와의 직접 관련성은 낮고, 규칙 기반 분류도 2025-02582를 'low_relevance'(분야 미지정)로 판정했다. 이 사례는 '관련 분야 보고서 소재'가 아니라 '날짜 역할·후속 규정 구분 능력' 검증용이며, 분야 관련성 평가는 1번 표의 나머지 문서로 한다.",
            "- 2025-02582 문서 본문에는 같은 날 게재된 다른 규칙(좌석벨트 알림 시스템)의 시행일 연기 문구가 함께 들어 있어, AI가 두 규칙을 섞지 않는지도 확인 대상이다."]
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
