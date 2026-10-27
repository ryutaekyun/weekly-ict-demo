# AI 소규모 검증 계획서 (실제 호출 전 · 승인 대기)

작성일 2026-10-27 · **이 문서는 계획일 뿐이며 실제 유료 AI 호출은 하지 않았다.** API 키 설정과 비용 승인 후 별도 지시에 따라 실행한다.

## 0. 전제

- 제공자/모델: Anthropic `claude-sonnet-5-5` (공식 모델 문서에 존재하는 ID). 단가: claude-sonnet-5-5: 입력 $2 / 출력 $10 (USD/100만 토큰) — 공식 모델 문서·가격표(platform.claude.com) 2026-10-27 확인값. 실제 사용 전 관리자 단가표에서 다시 확인.
- 비용 계산식: 입력 토큰 = 입력 문자 수 ÷ 2.5 + 지시문 900, 출력 토큰은 상한 가정 5,000(실제는 이보다 작을 수 있음), 비용 = 입력×단가 + 출력×단가. **추정치이며 제공자 청구금액이 아니다.**
- 분석 대상은 DB에 저장된 공개 공식 원문(Federal Register·arXiv 등)만 사용하며 비공개 원고·개인정보는 보내지 않는다.
- CI에서는 실제 호출을 하지 않는다. 실행은 사용자가 키를 설정하고 비용을 승인한 뒤 로컬 통합 사이트에서 수동으로 한다.

## 1. 공식 원문 단위 분석 (5건 이상)

| # | 구분 | 제목 | URL | 분석 목적 | 예상 입력/출력 토큰 | 예상 비용(USD) | 검증할 사실·날짜·수치 |
|---|---|---|---|---|---|---|---|
| 1 | 정책·규제 문서 | Modernizing the Commission's National Environmental Policy Act Rules | https://www.federalregister.gov/documents/2026/10/19/2026-21347/modernizing-the-commissions-national-environmental-policy-act-rules | 핵심 변화·일정·기관 입장 요약 정확성 | 5,701 / 5,000 | 0.0614 | 날짜 1993-10-04, 1999-08-10, 2000-11-09, 2001-05-22 / 수치 1.1200, 372724, 271001, 1.1206 |
| 2 | 정책·규제 문서 | Petition for Reconsideration of Action in Rulemaking Proceeding; Corre | https://www.federalregister.gov/documents/2026/10/19/2026-21312/petition-for-reconsideration-of-action-in-rulemaking-proceeding-correction | 핵심 변화·일정·기관 입장 요약 정확성 | 3,576 / 5,000 | 0.0572 | 날짜 2026-10-13, 2026-10-16, 2026-10-19, 2026-10-28 / 수치 372261, 271001, 372215, 372959 |
| 3 | 기술·연구 문서 | Navalia: Advancing Cowork Agents through Verifiable Task Synthesis and | https://arxiv.org/abs/2610.26887 | 연구 기여·수치 요약, 보고서 활용 가능성 | 5,701 / 5,000 | 0.0614 | 날짜 2026-10-13 / 수치 72510, 13.07, 13.20, 2211 |
| 4 | 기술·연구 문서 | Large language model and reinforcement learning based autonomous const | https://arxiv.org/abs/2610.26899 | 연구 기여·수치 요약, 보고서 활용 가능성 | 5,701 / 5,000 | 0.0614 | 날짜 2026-02-07 / 수치 2026, 19, 13, 17 |
| 5 | 후속 규정 사례(FMVSS 305a 시행일 변경) | Federal Motor Vehicle Safety Standards; FMVSS No. 305a Electric-Powere | https://www.federalregister.gov/documents/2024/12/20/2024-28707/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain | 발표일·시행일·준수 시한 구분 | 5,701 / 5,000 | 0.0614 | 날짜 2000-04-11, 2017-09-27, 2024-04-15, 2024-06-14 / 수치 104318, 265001, 104319, 10000 |
| 6 | 근거 부족 사례(원문이 짧음) | Authorized Translations of WCAG 2.2 and 2.1 in French updated | https://www.w3.org/news/2026/authorized-translations-of-wcag-2-2-and-2-1-in-french-updated/ | 근거 부족 시 보류·'근거 없음' 표시 | 1,254 / 5,000 | 0.0525 | 날짜 없음 / 수치 2.2 |

## 2. 복수 원문 이슈 종합 분석 (2건 이상)

| # | 이슈 | 원문 | 분석 목적 | 예상 입력/출력 | 예상 비용 | 검증할 사실 |
|---|---|---|---|---|---|---|
| 1 | National Artificial Intelligence Advisory Committee | National Artificial Intelligence Advisory Committe (2024-07-16) https://www.federalregister.gov/documents/2024/07/16/2024-15528/national-artificial-intelligence-advisory-committee<br>National Artificial Intelligence Advisory Committe (2024-08-20) https://www.federalregister.gov/documents/2024/08/20/2024-18596/national-artificial-intelligence-advisory-committee<br>National Artificial Intelligence Advisory Committe (2024-09-23) https://www.federalregister.gov/documents/2024/09/23/2024-21635/national-artificial-intelligence-advisory-committee<br>National Artificial Intelligence Advisory Committe (2024-11-04) https://www.federalregister.gov/documents/2024/11/04/2024-25571/national-artificial-intelligence-advisory-committee<br>National Artificial Intelligence Advisory Committe (2024-11-25) https://www.federalregister.gov/documents/2024/11/25/2024-27461/national-artificial-intelligence-advisory-committee | 논쟁이 없는 이슈에서 임의의 논쟁을 만들지 않는지, 발표일 순서·후속 변화 구분 | 21,029 / 5,000 | 0.0921 | 문서별 발표일·시행일·수치 대조 |
| 2 | Public Briefing on Changes to Advanced Computing and Semicon | Public Briefing on Changes to Advanced Computing a (2024-12-04) https://www.federalregister.gov/documents/2024/12/04/2024-28423/public-briefing-on-changes-to-advanced-computing-and-semiconductor-manufacturing-items<br>Additions and Modifications to the Entity List; Re (2024-12-05) https://www.federalregister.gov/documents/2024/12/05/2024-28267/additions-and-modifications-to-the-entity-list-removals-from-the-validated-end-user-veu-program<br>Foreign-Produced Direct Product Rule Additions, an (2024-12-05) https://www.federalregister.gov/documents/2024/12/05/2024-28270/foreign-produced-direct-product-rule-additions-and-refinements-to-controls-for-advanced-computing | 복수 기관·국가 입장 비교 시 근거 2건 이상 규칙 준수 | 13,058 / 5,000 | 0.0761 | 문서별 발표일·시행일·수치 대조 |

## 3. 후보주제 제안 (2건 이상)

| # | 대상 이슈 | 기존 후보주제 | 분석 목적 | 예상 입력/출력 | 예상 비용 |
|---|---|---|---|---|---|
| 1 | National Artificial Intelligence Advisory Committee | 1건(있으면 연결) | 선정 필요성·쟁점·국내 관련성의 근거 부족 표시, 임의 점수 미부여 | 21,029 / 5,000 | 0.0921 |
| 2 | Public Briefing on Changes to Advanced Computing and Semicon | 1건(있으면 연결) | 선정 필요성·쟁점·국내 관련성의 근거 부족 표시, 임의 점수 미부여 | 13,058 / 5,000 | 0.0761 |

## 4. 원고 초안 제안 (1건 이상)

| # | 대상 후보주제 | 분석 목적 | 예상 입력/출력 | 예상 비용 |
|---|---|---|---|---|
| 1 | National Artificial Intelligence Advisory Committee | 사실 문장 위주 초안의 근거 매핑률, 삽입 후 각주 미검증 상태 | 21,029 / 5,000 | 0.0921 |

## 5. 합계(추정)

- 입력 약 116,837 토큰 · 출력 상한 약 55,000 토큰 · **예상 비용 약 $0.78** (claude-sonnet-5-5 단가 기준, 상한 추정).
- 다른 모델(예: claude-haiku-5-5, claude-opus-5-5)을 쓰면 단가표(관리자 설정)에 맞춰 같은 식으로 다시 계산한다.
- 예상 소요 시간은 참고용: 요청당 수십 초~2분(원문 길이·출력량에 따라 다름).

## 6. 정상 결과 판단 기준

1. 사실(fact) 문장마다 원문 발췌문이 서버 대조에서 '원문 근거 확인'이고 날짜·수치가 발췌문과 일치한다.
2. '의미 불일치 가능성'(날짜 역할·단위·부등호·부정)이 연구원 검토에서 오탐 또는 정정 가능한 수준이다.
3. 단일 원문으로 국가 비교·논쟁을 만들지 않고, 근거가 없는 항목은 '근거 부족'으로 비워 둔다.
4. 후속 규정 사례에서 이미 변경된 시행일을 현재 사실로 쓰지 않는다.
5. 후보주제 제안이 국내 산업 관련성에 임의 점수를 붙이지 않는다.

## 7. 오류 판정 기준(검증 실패로 집계)

- 원문에 없는 발췌문(검증 실패), 값이 다른 문장(근거 불일치), 엉뚱한 문서에 연결된 근거, 사실 문장인데 근거 없음.
- 시행일·발표일·준수 시한을 혼동한 문장, 단위·부등호·부정이 뒤집힌 문장, 원문에 없는 논쟁·국가 입장, 국내 산업 영향 과장.
- 지표: 사실 문장 중 '근거 없음·불일치·검증 실패' 비율, 연구원이 정정한 문장 수, 과장·오류 사례 목록. **정확도를 100%라고 주장하지 않는다.**

## 8. 실행 순서(승인 후)

1. 서버 환경변수 `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`(필요 시 `AI_MODEL`) 설정 → 설정 화면 '연결 진단'으로 모델 사용 가능 확인(토큰 미사용).
2. 관리자 단가표 확인 → 위 대상 순서대로 한 건씩 실행(실행 전 예상 비용 확인 창에서 확인).
3. 결과를 원문과 대조해 오류 판정 기준에 따라 집계하고 보고한다.
