# AI 소규모 검증 계획서 (실제 호출 전 · 승인 대기)

작성일 2026-10-27 · **이 문서는 계획일 뿐이며 실제 유료 AI 호출은 하지 않았다.** API 키 설정과 사용자의 검증·비용 승인 후 별도 지시로만 실행한다.

## 0. 전제

- 제공자/모델: Anthropic `claude-sonnet-5-5`(공식 모델 문서에 존재). 단가: claude-sonnet-5-5: 입력 $2 / 출력 $10 (USD/100만 토큰) — 공식 모델 문서·가격표(platform.claude.com) 2026-10-27 확인값. 실제 사용 전 관리자 단가표에서 다시 확인.
- 비용 계산식: 입력 토큰 = 입력 문자 수 ÷ 2.5 + 지시문 900, 출력 토큰은 상한 가정 5,000, 비용 = 입력×단가 + 출력×단가. **추정치이며 제공자 청구금액이 아니다.** Sonnet 5.5는 적응형 사고가 기본이라 사고 토큰도 출력 토큰으로 과금되므로 실제 출력이 가정보다 클 수 있다(출력 한도 12,000토큰 이내).
- 원문은 호출당 문서 8건·문서당 앞 12,000자까지만 보낸다(그 이상은 '일부만 분석'으로 표시). 매우 긴 규정의 뒷부분 내용은 이번 검증 범위가 아니다.
- 분석 대상은 DB에 저장된 공개 공식 원문만 사용하며 비공개 원고·개인정보는 보내지 않는다. 총수량을 맞추려고 무관한 행정공고(라디오·TV 방송국 허가, 정보수집 승인 요청, 정정 공고 등)는 넣지 않았다.
- 안전장치: 실제 호출은 관리자 1건 승인(대상·모델·예산 상한 지정, 1회용)이 있어야 하고, 예상 비용이 상한을 넘으면 호출 전에 차단되며, 자동 재시도·나머지 문서 자동 분석은 없다.

## 1. 공식 원문 단위 분석

| # | 구분 | 제목 | URL / 접근 | ICT 분야·활용가치 | 발표일·시행·정정 | 원문 확보 | 분석 목적 | 선정 이유 | 예상 입력/출력 토큰 | 예상 비용 | 검증할 사실·날짜·수치 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 정책·규제 — 통신·주파수 | Upper C-Band (3.98-4.2 GHz); Expanding Flexible Use of the 3.7 to 4.2  | https://www.federalregister.gov/documents/2026/10/19/2026-21324/upper-c-band-398-42-ghz-expanding-flexible-use-of-the-37-to-42-ghz-band (HTTP 200) | bcast · priority | 2026-10-19 · 유형 Rule · 발표 2026-10-19 · 시행 2026-10-19 | 10,446자(보냄 10,446자) | 핵심 변경·일정·기관 입장 요약 정확성 | FCC의 3.7–4.2 GHz 대역 유연 사용 규제 — 실제 ICT(통신) 정책자료·공식 1차 출처·짧은 원문, **첫 실호출 대상** | 5,079 / 5,000 | $0.0602 | 날짜 1995-10-01, 2016-07-01, 2017-10-02, 2018-08-03 / 수치 27.1412, 27.1419, 540000, 372601 |
| 2 | 정책·규제 — 사이버보안 | Request for Information (RFI) on Modernizing the National Vulnerabilit | https://www.federalregister.gov/documents/2026/08/12/2026-16371/request-for-information-rfi-on-modernizing-the-national-vulnerability-database-in-the-age-of (HTTP 200) | sec · priority | 2026-08-12 · 유형 Notice · 발표 2026-08-12 | 20,616자(보냄 12,000자) | RFI의 질의 항목·마감일·대상 구분 | NIST 취약점 데이터베이스 현대화 RFI — 보안 정책 자료 | 5,701 / 5,000 | $0.0614 | 날짜 2026-08-06, 2026-08-11, 2026-08-12, 2026-10-13 / 수치 351.305, 351.212, 351.213, 351.221 |
| 3 | 정책·규제 — 반도체 수출통제 | Foreign-Produced Direct Product Rule Additions, and Refinements to Con | https://www.federalregister.gov/documents/2024/12/05/2024-28270/foreign-produced-direct-product-rule-additions-and-refinements-to-controls-for-advanced-computing (HTTP 200) | semi · general | 2024-12-05 · 유형 Rule · 발표 2024-12-05 · 시행 2024-12-02 | 306,390자(보냄 12,000자) | 복잡한 규정의 적용 대상·시행일·예외 구분(원문 앞 12,000자 한도 확인) | BIS 첨단 컴퓨팅·반도체 제조 장비 수출통제 — 반도체 정책 핵심 문서(원문이 매우 길어 절단 표시 검증 포함) | 5,701 / 5,000 | $0.0614 | 날짜 2022-10-07, 2022-10-13, 2023-10-25, 2024-12-02 / 수치 734.19, 241126, 265001, 62186 |
| 4 | 기술·연구 — AI | Ask to Distill: Learning to Synthesize Data for On-Policy Distillation | https://arxiv.org/abs/2610.27450 (HTTP 200) | ai · priority | 2026-10-22 · 연방관보 아님 | 115,871자(보냄 12,000자) | 연구 기여·수치 요약, 보고서 활용 가능성 | 활용가치 '우선' 판정을 받은 AI 연구 논문 | 5,701 / 5,000 | $0.0614 | 날짜 2026-10-20, 2026-10-21 / 수치 2610.27450, 181.7, 1021, 2025 |
| 5 | 기술·연구 — AI 보안 | PROVISO: Provenance-Informed Action Selection for Secure LLM Agents | https://arxiv.org/abs/2610.27115 (HTTP 200) | ai · general | 2026-10-22 · 연방관보 아님 | 101,485자(보냄 12,000자) | 연구 방법·결과 수치 요약, 과장 여부 | LLM 에이전트 보안 연구 논문 | 5,701 / 5,000 | $0.0614 | 날짜 2026-10-19 / 수치 2610.27115, 13.84, 2025, 7.07 |
| 6 | 후속 규정 — FMVSS 305a 시행일 연기 | Federal Motor Vehicle Safety Standards; FMVSS No. 305a Electric-Powere | https://www.federalregister.gov/documents/2025/02/14/2025-02582/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain (HTTP 200) | - · low_relevance | 2025-02-14 · 유형 Rule · 발표 2025-02-14 · 시행 2025-03-20 | 11,171자(보냄 11,171자) | 발표일·시행일·준수 시한 구분, 후속 규정이 바꾼 것과 바꾸지 않은 것 구분 | 2024-28707 최종 규정의 시행일을 2025.3.20.으로 연기한 공식 후속 규정(분량 작음) | 5,369 / 5,000 | $0.0607 | 날짜 2015-04-15, 2024-10-01, 2024-12-20, 2025-01-03 / 수치 155.420, 104318, 265001, 501.5 |
| 7 | 근거 부족 — 원문 전문 없음 | NIST Launches Centers for AI in Manufacturing and Critical Infrastruct | https://www.nist.gov/news-events/news/2025/12/nist-launches-centers-ai-manufacturing-and-critical-infrastructure (HTTP 200) | ai · needs_more_info | 2025-12-22 | 없음(분석 보류 대상) | 원문 전문이 없을 때 호출 없이 '분석 보류'(비용 0)가 되는지 | AI 관련 NIST 보도자료이나 전문 추출이 이루어지지 않은 실제 사례 — 호출 비용이 들지 않는 안전 검증 | 호출 안 함 | $0 | 보류 메시지·근거 부족 표시 |

## 2. FMVSS 305a 후속 규정 비교 시나리오 (복수 원문 이슈 #1)

같은 이슈를 입력 문서 범위만 바꿔 세 번 분석해, AI가 기존 규정만 인용할 때와 후속 규정까지 반영할 때를 비교한다.

| 시나리오 | 입력 문서 | 기대(정상) 결과 | 오류 판정 | 예상 입력/출력 | 예상 비용 |
|---|---|---|---|---|---|
| S1 기존 규정만 | Federal Motor Vehicle Safety Standards;  2024-12-20 https://www.federalregister.gov/documents/2024/12/20/2024-28707/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain | 시행일 2025-02-18, 준수 시한 2025-12-22(비상대응 문서화)·2027-09-01(4,536 kg 이하)·2028-09-01(초과)을 구분해 서술하되 '후속 변경 여부 확인 필요'(gap)를 남긴다 | 후속 문서 없이 '시행일이 연기되었다'고 단정하면 오류(원문 근거 없음) | 5,701 / 5,000 | $0.0614 |
| S2 후속 규정 포함 | Federal Motor Vehicle Safety Standards;  2024-12-20 https://www.federalregister.gov/documents/2024/12/20/2024-28707/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain<br>Federal Motor Vehicle Safety Standards;  2025-02-14 https://www.federalregister.gov/documents/2025/02/14/2025-02582/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain | 시행일은 2025-03-20으로 연기됨을 근거와 함께 쓰고, 2025-02-18을 현재 사실로 쓰지 않는다. 준수 시한은 후속 문서가 바꾼다고 하지 않았음을 구분 | 2025-02-18을 현재 시행일로 서술, 준수 시한을 연기된 것으로 서술하면 오류 | 10,169 / 5,000 | $0.0703 |
| S3 이후 개정 포함 | Federal Motor Vehicle Safety Standards;  2024-12-20 https://www.federalregister.gov/documents/2024/12/20/2024-28707/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain<br>Federal Motor Vehicle Safety Standards;  2025-02-14 https://www.federalregister.gov/documents/2025/02/14/2025-02582/federal-motor-vehicle-safety-standards-fmvss-no-305a-electric-powered-vehicles-electric-powertrain<br>Federal Motor Vehicle Safety Standard No 2026-06-03 https://www.federalregister.gov/documents/2026/06/03/2026-11072/federal-motor-vehicle-safety-standard-no-214-side-impact-protection-federal-motor-vehicle-safety | 2026-06-03 규정(2026-07-06 시행)은 별도 규칙의 일부로 305a S9.3 문구만 개정했음(요건 변경 없음)을 구분하고, 'mandatory applicability begins on September 1, 2027'을 시행일과 혼동하지 않는다 | 개정 규정의 시행일(2026-07-06)을 305a 시행·준수일로 혼동하면 오류 | 14,969 / 5,000 | $0.0799 |

- 관련 사실(공식 원문 확인): 2024-28707(2024-12-20) 최종 규정 — 시행일 2025-02-18, 준수 시한 2025-12-22(비상대응 문서화)·2027-09-01(GVWR 4,536 kg 이하)·2028-09-01(초과). 2025-02582(2025-02-14) — 시행일을 2025-03-20까지 연기(준수 시한 변경은 언급 없음). 2026-11072(2026-06-03, 시행 2026-07-06) — FMVSS 214 정리 규칙의 일부로 305a S9.3 참조 문구 개정, 요건 변경 없음.
- Federal Register에서 2025-02582 이후 같은 문서번호 체계(Docket NHTSA-2024-0091)의 추가 후속 문서는 확인되지 않았고, 2026-11072만 305a를 개정한다(2026-10-27 조회).

## 3. 복수 원문 이슈 #2 — 논쟁이 없는 이슈

| 이슈 | 원문 | 분석 목적 | 예상 입력/출력 | 예상 비용 | 검증할 사실 |
|---|---|---|---|---|---|
| Group Registration of Updates to a News Website (저작권청, 콘텐츠·미디어) | Group Registration of Updates to a News Website 2026-05-28 https://www.federalregister.gov/documents/2026/05/28/2026-10604/group-registration-of-updates-to-a-news-website<br>Group Registration of Updates to a News Website 2026-08-13 https://www.federalregister.gov/documents/2026/08/13/2026-16465/group-registration-of-updates-to-a-news-website | 제안 규칙과 후속 문서의 변경점만 정리하고 **임의의 논쟁·국가별 입장을 만들지 않는지**, 발표일 순서 구분 | 8,301 / 5,000 | $0.0666 | 문서별 발표일·마감일·조항 수치 대조 |

## 4. 후보주제 제안 (2건)

| # | 대상 이슈 | 기존 후보 | 분석 목적 | 예상 입력/출력 | 예상 비용 |
|---|---|---|---|---|---|
| 1 | FMVSS 305a(S2 범위: 2024-28707 + 2025-02582) | 5건(있으면 연결) | 선정 필요성·쟁점·국내 관련성의 '근거 부족' 표시, 임의 점수 미부여 | 10,169 / 5,000 | $0.0703 |
| 2 | Group Registration of Updates to a News Website | 1건(있으면 연결) | 선정 필요성·쟁점·국내 관련성의 '근거 부족' 표시, 임의 점수 미부여 | 8,301 / 5,000 | $0.0666 |

## 5. 원고 초안 제안 (1건)

| 대상 후보주제 | 입력 범위 | 분석 목적 | 예상 입력/출력 | 예상 비용 |
|---|---|---|---|---|
| Federal Motor Vehicle Safety Standards; FMVSS No. 305a Electric-Powere | 2024-28707 + 2025-02582 | 시행일 연기를 반영한 사실 문장 초안의 근거 매핑률, 삽입 후 각주 미검증 상태, 원문 변경 재검토 연계 | 10,169 / 5,000 | $0.0703 |

## 6. 비용 합계(추정·상한)

- 전체 계획: 입력 약 101,031 토큰 · 출력 상한 약 65,000 토큰 · **예상 비용 약 $0.85** (claude-sonnet-5-5 단가 기준).
- **최초 실호출 1건(권장)**: Upper C-Band (3.98-4.2 GHz); Expanding Flexible Use of the 3 (https://www.federalregister.gov/documents/2026/10/19/2026-21324/upper-c-band-398-42-ghz-expanding-flexible-use-of-the-37-to-42-ghz-band) — 예상 입력 5,079 / 출력 상한 5,000 토큰, **예상 비용 약 $0.0602**. 최대 계산 비용(출력 12,000토큰 가정)과 권장 승인 상한은 사전 점검 화면에서 확인한다(제안: 첫 호출 상한 $0.15 이내).
- 요청별 상한: 관리자 승인마다 예산 상한을 지정하고, 전역 상한(`AI_MAX_COST_PER_REQUEST_USD`)을 둘 수 있다. 예상 비용이 상한을 넘으면 호출 전에 차단된다.
- 예상 소요 시간(참고): 요청당 수십 초~2분. 다른 모델을 쓰면 단가표에 맞춰 다시 계산한다.

## 7. 품질 평가(실제 호출 후 연구원이 7개 항목으로 평가)

① 원문 핵심 내용 요약 정확성 ② 날짜·수치·단위·적용대상 정확성 ③ 기존 정책과 후속 변경 구분 ④ 모든 핵심 사실의 원문 근거 ⑤ 원문에 없는 논쟁·국가별 입장 생성 여부 ⑥ 국내 산업 영향·추가 검토 사항 구분 ⑦ 보고서 원고 활용 가능성.
- 평가는 분석 화면의 '품질 평가'에 저장되며, **모의 응답 평가와 실제 AI 평가는 합산하지 않고** 설정 화면에서 따로 집계된다.
- 함께 기록: 의미 불일치 사례(날짜 역할·단위·부등호·부정), 근거 부족 사례, 잘못된 출처 연결 사례, 사실 문장 중 근거 없음·불일치·검증 실패 비율. **정확도를 100%라고 주장하지 않는다.**

### 정상 결과 기준

1. 사실 문장마다 원문 발췌문이 서버 대조에서 '원문 근거 확인'이고 날짜·수치가 발췌문과 일치한다.
2. '의미 불일치 가능성' 표시가 연구원 검토에서 오탐이거나 정정 가능한 수준이다.
3. 단일 원문으로 국가 비교·논쟁을 만들지 않고 근거가 없는 항목은 비워 '근거 부족'으로 둔다.
4. 후속 규정 시나리오에서 이미 변경된 시행일을 현재 사실로 쓰지 않는다.
5. 후보주제 제안이 국내 산업 관련성에 임의 점수를 붙이지 않는다.

### 오류 판정 기준

- 원문에 없는 발췌문(검증 실패), 값이 다른 문장(근거 불일치), 엉뚱한 문서에 연결된 근거, 사실 문장인데 근거 없음.
- 시행일·발표일·준수 시한 혼동, 단위·부등호·부정 반전, 원문에 없는 논쟁·국가 입장, 국내 산업 영향 과장.

## 8. 실행 순서(승인 후 · 한 번에 한 건)

1. 서버 환경변수 설정(`docs/AI_SETUP.md`) → 설정 화면 '연결 진단'(모델 목록 조회, 토큰 미사용)으로 모델 사용 가능 확인.
2. 사용자 검증·비용 승인 → 관리자가 위 '최초 실호출 1건'을 화면에서 1건 승인(예산 상한 지정) → 실행 → 실제 토큰·계산 비용·오류 보고(제공자 청구금액과 구분).
3. 결과를 원문과 대조해 품질 평가 저장 → 이상이 없으면 사용자가 다음 대상을 다시 승인(자동으로 나머지 문서를 분석하지 않는다).

## 9. 이번 점검에서 확인한 한계

- BIS 수출통제 규정처럼 매우 긴 원문은 앞 12,000자만 분석되므로 뒤쪽 조항의 정확성은 이번 검증 범위가 아니다(화면에 '일부만 분석' 표시).
- ICT 관련성 주의: FMVSS 305a는 사용자가 지정한 후속 규정 처리 검증 시나리오다. 전기차 동력계 안전기준이라 ICT 9대 분야(SW·자율주행 등)와의 직접 관련성은 낮고, 규칙 기반 분류도 2025-02582를 'low_relevance'(분야 미지정)로 판정했다. 이 사례는 '관련 분야 보고서 소재'가 아니라 '날짜 역할·후속 규정 구분 능력' 검증용이며, 분야 관련성 평가는 1번 표의 나머지 문서로 한다.
- 2025-02582 문서 본문에는 같은 날 게재된 다른 규칙(좌석벨트 알림 시스템)의 시행일 연기 문구가 함께 들어 있어, AI가 두 규칙을 섞지 않는지도 확인 대상이다.
