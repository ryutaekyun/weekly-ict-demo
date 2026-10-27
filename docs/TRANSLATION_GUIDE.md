# 한글 번역 가이드

**상태: Phase 4-3에서 구현 예정(미구현).** 유료 번역 API(Google·DeepL·OpenAI·Anthropic 등)와 비공식 번역 웹 호출은 사용하지 않는다. 오프라인 엔진(Argos Translate 우선, LibreTranslate 자체 호스팅 대안)의 설치·라이선스·영/일/중 실제 시험 결과는 4-3에서 이 문서에 기록한다. 시험 전에는 지원 언어를 표시하지 않으며, 현재 화면의 '번역(준비 중)' 버튼은 비활성이다.

## Phase 4-2에서 준비한 번역 연계 데이터 구조
수집 단계에서 이미 저장하는 값(번역 단계가 그대로 사용):
| 필드(`source_documents`) | 용도 |
|---|---|
| `language` (ko/en/ja/zh/und) | 번역 모델 선택 — 수집 시 제목·초록으로 간이 판별(번역 단계에서 정확도 검증 예정) |
| `title`, `raw_text`(초록·요약) | 번역 대상 원문(수정하지 않음, 원문 보존) |
| `content_hash` | 원문 변경 감지 — 번역 시점의 해시와 다르면 '재번역 필요' |
| `version_no`, `is_latest`, `previous_version_id` | 번역은 버전별로 보존, 최신 버전 기준 표시 |
| `document_full_text.full_text` | 확보된 전문(문단 단위 번역 입력) |
| `external_id`, `origin_url` | 번역문을 인용할 때 원문 출처·링크 유지 |

4-3에서 추가할 표(설계안):
- `document_translations`: id, document_id, source_version_no, source_content_hash, source_lang, target_lang(ko), scope(title|abstract|body|selection), engine, engine_version, route(direct|via_en), machine_text, reviewed(bool), edited_text, edited_by, edited_at, needs_retranslation(bool), status(pending|running|done|failed), error, created_at.
- `translation_paragraphs`: translation_id, idx, source_text, machine_text, edited_text — 긴 문서를 문단 단위로 백그라운드 번역·진행률 표시.
- `translation_glossary`: term_src, term_ko, field_code, note — ICT 전문용어 사전(예: Large Language Model → 거대언어모델), 기관·법령명 원어 병기.
- 규칙: 자동번역은 '자동번역 — 원문 확인 필요'로 표시하고 사실 검증 완료로 처리하지 않는다. 날짜·수치·단위·정책 명칭은 원문 대조를 요구한다. 번역 실패 시 원문 유지·재시도. 같은 원문 해시는 재번역하지 않는다. 번역은 `collection_jobs`와 같은 작업 큐(작업자)로 실행한다.
