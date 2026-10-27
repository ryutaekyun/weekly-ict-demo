# TNP AI Platform — weekly-ict-demo

이 저장소는 두 개의 서로 다른 산출물을 담고 있다.

1. **`index.html`** — IITP 제안 발표용 공개 시연 데모. GitHub Pages로 그대로 서빙되며 **이번 작업으로 전혀 손대지 않았다**.
2. **`apps/`** — 실제 운영을 목표로 새로 짓기 시작한 Next.js + FastAPI + PostgreSQL 시스템. 아래는 이 시스템에 대한 안내다.

> 전체 설계 배경·DB 스키마·로드맵은 [`docs/PLATFORM_PLAN.md`](./docs/PLATFORM_PLAN.md), 기존 데모 기능 전수 감사는 [`docs/FEATURE_AUDIT.md`](./docs/FEATURE_AUDIT.md) 참고.

## 지금 상태 — 무엇이 실제로 되고, 무엇이 안 되는지

| 항목 | 상태 |
|---|---|
| FastAPI 백엔드(인증 + 후보주제 CRUD + 검토/승인) | **구현·실행·테스트 완료** — 초기 29개에서 Phase 3-2 기준 `pytest` 전부 통과(LibreOffice 포함 환경에서 PDF 렌더링 테스트까지 실행), 실제 서버 기동 후 curl로 end-to-end 확인함 |
| 인증 보안(httpOnly 쿠키, CSRF, 로그인 잠금, 비밀번호 변경) | **구현·테스트 완료** — 쿠키/CSRF/계정잠금/비밀번호변경 각각 자동 테스트로 확인(아래 "보안 관련 알려진 사항" 참고) |
| PostgreSQL 스키마(14개 테이블 + 로그인 잠금·출처/문서 메타데이터 확장) + Alembic 마이그레이션 다수(최신: Phase 3-1 원고 작업실) | **구현 완료** — SQLite로 실제 `alembic upgrade head` 성공 확인(Postgres 자체는 이 작업 환경에 설치되어 있지 않아 미설치 상태로 검증) |
| 로컬 개발용 더미 계정 시드 | **구현·실행 완료** — 전부 가상 인물, 비밀번호는 실행마다 무작위 생성 |
| Next.js 실제 운영 웹사이트(대시보드·ICT정보수집·핵심이슈분석·후보주제·출처관리·설정, 7개 메뉴) | **구현·빌드·실행·브라우저 검증 완료** — winget으로 Node.js(LTS v24.20.0)를 직접 설치해 `npm run build`/`npm run dev` 실행, 실데이터(255건) 기준 로그인·조회·수정·저장·새로고침 후 반영·서버 재시작 후 데이터 유지·권한 차단까지 전부 실제 브라우저로 확인. Playwright E2E 6건(시나리오 A~F) 전부 통과. 상세는 `docs/PLATFORM_PLAN.md` §10 참고 |
| Docker Compose(db+api+web) | **설정 파일 작성 완료, 로컬 미설치로 실행 미검증** — 이 작업 환경에 Docker가 설치되어 있지 않다. PostgreSQL 통합 자체는 GitHub Actions CI(`postgres:16-alpine` 서비스 컨테이너)에서 Alembic 마이그레이션+전체 테스트로 검증했다 |
| 다방식(RSS+API) 수집 엔진 — ICT 9대 분야 전체 | **구현·실행 완료 — 9대 분야 전부 최소 1곳(총 10개 출처)에서 실시간 수집 성공 확인**, 255건 실제 DB 저장·재수집 중복방지·404 오류분류까지 라이브 검증. 상세는 `docs/PLATFORM_PLAN.md` §7 참고 |
| 문서별 원문 전문 추출(HTML+PDF) + ICT 분야 자동분류(출처 고정분야와 분리) + 실무 활용가치 판정 + 핵심내용 구조화 + AI 연동(공급자 미설정 시 규칙기반 폴백) | **구현·실행 완료 — 기존 255건 전체 재처리, 전문추출 215건 성공, 35건이 출처 고정분야와 다르게 재분류됨(Phase 2-1 결함 수정 확인)**. 실데이터 검증 중 발견한 실제 결함 3건(단위 오매칭, 기술표준 오분류, PDF 핵심내용 추출 오류)도 전부 수정. AI는 키 미보유로 실호출 미검증(규칙 기반으로만 동작 확인). 상세는 `docs/PLATFORM_PLAN.md` §8 참고 |
| 동일 이슈 자동 통합(RIN/Docket 강한신호+제목유사도 약한신호) + 신규·후속변화 타임라인 + 쟁점·논쟁 분석 + 후보주제 가중점수 추천 | **구현·실행 완료 — 161건 실데이터로 143개 이슈 클러스터 생성(복수문서 통합 13건), 142건 후보주제 추천**. 실데이터 검증 중 발견한 실제 결함 7건(세션 flush 문제, 분야오분류로 인한 클러스터링 실패, 관용구 오탐, 허브문서 자동확정 등) 전부 수정. 국가비교·국내산업연관성은 근거 없이 임의 작성하지 않고 142건 전부 정직하게 "평가보류" 처리. AI는 Phase 2-2와 동일하게 키 미보유로 실호출 미검증. 상세는 `docs/PLATFORM_PLAN.md` §9 참고 |
| 연구·집필 작업실(후보주제→원고 생성, TipTap 편집기, 자동저장·주요버전·비교·복원, 각주-원문 근거 연결, 교차검토·내부 승인, 낙관적 잠금 충돌 감지) | **구현·실행·검증 완료 (Phase 3-1)** — 백엔드 테스트 108개, Playwright 시나리오 A~G 전부 통과. 근거 미검증 각주는 연구원이 명시 확인하기 전까지 검증완료가 되지 않음. 내부 승인은 IITP 공식 선정과 분리. 실제 공식 원문(연방관보 FMVSS 305a) 기반 '시범 작성 원고' 1건 작성. 상세는 `docs/PLATFORM_PLAN.md` §11 |
| 보고서·요약본 제작(일반호·특집호·요약본 구성, 실제 Word 각주·표·목차가 있는 편집 가능 DOCX + LibreOffice 변환 PDF, 스냅샷 출력 이력·SHA-256, 발간 점검, 출력용 확정) | **구현·실행·검증 완료 (Phase 3-2)** — 실제 파일을 열어 확인하고 PDF를 페이지별로 렌더링해 점검. 본문 각주 번호 `[n]` 표시. **Microsoft Word 실제 열람은 미검증**, 공식 IITP 양식이 없어 임시 표준 템플릿 사용(IITP 공식 확인과 별개). 상세는 `docs/PLATFORM_PLAN.md` §12 |
| 카드뉴스 제작(보고서·요약본 연계 생성, 디자인 템플릿 4종, 3분할 웹 편집기, 원문 근거·검증, 검토·승인·버전, **편집 가능한 PPTX** + 고화질 PNG) | **구현·실행·검증 완료 (Phase 3-3)** — PPTX는 텍스트·도형·표·차트가 PowerPoint 객체(전체 이미지 아님), PNG는 같은 PPTX를 LibreOffice로 렌더링(짧은 변 1,000px 이상). 기본 규격 7×15.62cm는 작업용 값. **Microsoft PowerPoint 실제 열람은 미검증**, 이미지·AI 생성 미구현. 상세는 `docs/PLATFORM_PLAN.md` §13 |
| 후속 규정 알림(근거 원문을 바꾸는 후속 공식 문서 등록 → 영향받는 원고·보고서·카드뉴스에 재검토 표시, 자동 수정·자동 검증 없음) + 카드뉴스 품질 보완(출처 하이퍼링크, 합성 표시, 빈 항목 제거) | **구현·실행·검증 완료 (Phase 3-3.1)** — FMVSS 305a 시행일 연기(2025.2.18.→2025.3.20.)를 연방관보 공식 원문으로 확인해 시범 원고·카드뉴스에 반영하는 흐름을 실제 데이터로 수행. 상세는 `docs/PLATFORM_PLAN.md` §15 |
| 주간기술동향지 편집(연간 25회 계획·편집 일정, 외부 전문가 DB, 원고 의뢰, 외부 저자 포털 제출·보안 검사, 검토·저자 수정·심의, 버전 비교, 교정, 임시 템플릿 DOCX/PDF 발간본) | **구현·실행·검증 완료 (Phase 3-4)** — 실제 브라우저 E2E와 합성 시범 업무(가상 집필진 2명·원고 2건)로 확인. **실제 이메일 발송·IITP 업로드 없음**, 표절검사 서비스 미연동, Microsoft Word 실제 호환 미검증, 저자 원고의 그림·각주는 발간본에 자동 변환되지 않음. 상세는 `docs/PLATFORM_PLAN.md` §16 |
| 시연 통합·원문 링크·요약본 사실 재검토·심의 확정 통제·공개 `/preview/` | **구현·실행·검증 완료 (Phase 3-5)** — 뉴스 제목 클릭 시 공식 원문 새 탭(주소 없음은 차단+사유), 필터·정렬·건수·뒤로가기 유지, 빈 분야 처리, 이슈 병합·분리, 후보 수정 이력, 요약본 핵심 사실(시행일) 변경 비교와 검토자 판단 기록, 미해결 필수 심의의견 확정 차단(예외는 승인권자+사유), 읽기 전용 공개 스냅샷 `preview/`(개인정보·검토의견·원문 전문 제외). pytest 225건·Playwright 26건 통과. Word·PowerPoint 실열람 미검증. 화면별 상태는 `docs/FEATURE_AUDIT.md` 하단, 상세는 `docs/PLATFORM_PLAN.md` §17 |
| 원문 근거 기반 AI 분석(문서·이슈 심층분석·후보주제 제안·원고 초안 보조, 근거 검증, 연구원 검증, 비용·권한·재사용 통제) | **구현 완료 / 실제 AI 호출 미검증 (Phase 3-6)** — AI API 키가 없어 모의 응답으로만 pytest 241건·Playwright 32건을 통과했고(3-6.1에서 269건·36건으로 증가), 실제 LLM 호출·정확도는 검증하지 않았다(키 미설정 시 '설정 필요'만 표시, 가짜 결과 없음). AI는 후보 상태·기존 원고를 바꾸지 않으며 발췌문·날짜·수치를 서버가 원문과 대조한다. 상세는 `docs/PLATFORM_PLAN.md` §18 |
| AI 분석·원고 집필 안정화(원문 변경 시 AI 삽입 문장 재검토, 의미 불일치 탐지, 삽입 위치 선택·취소, 공급자 오류 분류, 관리자 단가표·사용량·연결 진단, 실제 AI 검증 계획서) | **구현 완료 / 실제 AI 호출 미검증 (Phase 3-6.1)** — 모든 검증은 모의 응답·모의 HTTP이며 pytest 269건·Playwright 36건 통과. 실제 LLM 호출·정확도·실제 비용은 키와 비용 승인 후 `docs/AI_VALIDATION_PLAN.md`대로 검증해야 한다. 상세는 `docs/PLATFORM_PLAN.md` §19 |
| HTML 파싱 수집기(Federal Register 외), 분야별 2곳 이상 확보, 실제 AI 모델 호출, HWPX 출력, 주간기술동향지·발간·배포 관리, 실제 메일 발송 | **미구현** (Phase 3-4 이후, `docs/PLATFORM_PLAN.md`의 로드맵 참고) |

**Next.js 빌드/구동은 Phase 2-4에서 실제로 검증 완료**(winget으로 Node.js를 직접 설치해 빌드·실행·브라우저 테스트까지 수행, `docs/PLATFORM_PLAN.md` §10 참고). **Docker Compose 전체 스택만 사용자 환경에서 처음 실행·검증이 필요**하다(PostgreSQL 통합 자체는 GitHub Actions CI로 검증됨).

## 백엔드 단독 실행 (이미 이 환경에서 검증됨)

```bash
cd apps/api
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt

cp .env.example .env            # 로컬 테스트는 DATABASE_URL=sqlite:///./dev.db 로 바꿔도 됨
export PYTHONPATH=.
python -m alembic upgrade head
python -m app.seed              # 가상 더미 계정 생성, 비밀번호는 실행할 때마다 무작위 생성되어 콘솔에 1회만 출력됨
uvicorn app.main:app --reload
```

- `GET http://localhost:8000/health` → `{"status":"ok"}`
- `POST http://localhost:8000/auth/login` — 이메일/비밀번호는 위 `app.seed` 실행 시 콘솔에 출력된 더미 계정 값을 사용(코드에 고정값 없음)

### 테스트

```bash
cd apps/api
PYTHONPATH=. pytest -v
```

마지막 실행 결과: **97 passed**. 테스트는 기본적으로 SQLite 인메모리 DB를 사용하지만, `TEST_DATABASE_URL` 환경변수를 PostgreSQL 접속 문자열로 지정하면 동일한 스위트가 그대로 PostgreSQL에서도 통과한다(GitHub Actions CI `backend-postgres` 잡이 매번 이렇게 실행한다). 수집 엔진 테스트는 네트워크 호출을 모킹해 로직(신규/중복/개정판/실패/반복실패시 needs_review)만 검증하고, 인증 보안 테스트는 쿠키·CSRF·계정잠금·비밀번호변경을 각각 확인한다. Phase 2-2 분류·전문추출·가치판정·구조화·AI연동 테스트는 `tests/test_classification.py`, `test_extraction.py`, `test_value_assessment.py`, `test_structured_extract.py`, `test_ai_service.py`, `test_documents_api.py` 참고. Phase 2-3 이슈통합·타임라인·쟁점분석·후보추천 테스트는 `tests/test_issue_clustering.py`, `test_issue_timeline.py`, `test_issue_analysis.py`, `test_candidate_recommendation.py`, `test_issues_api.py` 참고. Phase 2-4 문서목록·대시보드·후보점수 테스트는 `tests/test_documents_list_and_dashboard.py`, `test_candidate_detail_score.py` 참고. 실제 네트워크를 통한 라이브 검증 결과는 `docs/PLATFORM_PLAN.md` §7-2, §8-3·8-4, §9-3·9-4 참고.

### 출처 수집 실행

```bash
python -m app.seed_sources         # ICT 9대 분야 검증된 공식 출처 10곳 등록(분야당 최소 1곳)
python -m app.run_all_collections  # 등록된 모든 활성 출처에 대해 1회 수집 실행
# 이후 POST /sources/{id}/collect 로 출처 1곳만 재수집(관리자/승인자/검토자 권한)
```

### 문서 분석(전문추출·분류·가치판정·구조화) 실행

```bash
python -m app.reprocess_documents             # 기존 수집 문서 전체에 Phase 2-2 파이프라인 적용
python -m app.reprocess_documents --field ai  # 특정 분야(출처 기준)만 재처리
# 이후 POST /documents/{id}/process 로 문서 1건만 재실행(관리자/승인자/검토자 권한)
# 연구원 수정: PATCH /documents/{id}/classification, PATCH /documents/{id}/value-assessment
```

### 이슈 통합·쟁점분석·후보주제 추천 실행(Phase 2-3)

```bash
python -m app.reprocess_issues   # 분류된(관련성=matched) 문서 전체를 이슈 클러스터로 통합하고 분석·추천까지 실행
# 이후 POST /issues/cluster/{document_id}, POST /issues/{id}/analyze, POST /issues/{id}/recommend 로 개별 실행
# 연구원 수정: PATCH /issues/{id}/merge(병합), POST /issues/split(분리)
# 가중치 조정(관리자 전용): GET·PATCH /issues/scoring/config
```

### 보고서 PDF 출력에 필요한 도구 (Phase 3-2)
DOCX는 추가 도구 없이 생성되지만, **PDF 변환·페이지 수/목차 번호 확인에는 LibreOffice가 필요**하다. 없으면 PDF는 "생성 불가"로 실패 기록되고 DOCX의 목차에는 페이지 번호가 들어가지 않는다(번호를 임의로 만들지 않음).
`soffice`가 PATH에 있거나 `SOFFICE_PATH` 환경변수로 경로를 지정한다(Windows는 공식 MSI를 사용자 폴더에 풀어 쓸 수 있음). 한글 글꼴은 Windows는 맑은 고딕, CI(Ubuntu)는 `fonts-noto-cjk`(OFL) + fontconfig 별칭을 사용한다 — `.github/scripts/install_report_tools.sh` 참고.
시범 출력물 재생성: `python -m app.create_pilot_manuscript` → `python -m app.create_pilot_reports <출력폴더>` → `python -m app.create_pilot_card_news <출력폴더>`

## 전체 스택 (Docker Compose) — 사용자 환경에서 처음 실행·검증 필요

```bash
cp apps/api/.env.example apps/api/.env
docker compose -f infra/docker-compose.yml up --build
```

- Postgres: `localhost:5432` (user/pass/db: `tnp`/`tnp_password`/`tnp_platform`)
- API: `http://localhost:8000`
- Web: `http://localhost:3000`

최초 기동 후 시드 실행:

```bash
docker compose -f infra/docker-compose.yml exec api python -m app.seed
```

## 프런트엔드 단독 실행 (Phase 2-4에서 실제 빌드·실행·브라우저 검증 완료)

```bash
cd apps/web
npm install
npm run dev     # http://localhost:3000, 백엔드가 http://localhost:8000에서 떠 있어야 함
npm run build   # 프로덕션 빌드 — Phase 2-4에서 실제 성공 확인(Next.js 16.4.2)
```

`NEXT_PUBLIC_API_URL`(기본 `http://localhost:8000`)을 바꾸려면 `.env.local`에 설정.

### 브라우저 E2E 테스트(Playwright)

```bash
cd apps/api
python -m app.seed_e2e_test_user   # 고정 비밀번호 테스트 계정 생성(E2E 전용, 운영 계정 아님)

cd ../web
npx playwright install chromium
npm run test:e2e   # 백엔드(8000)·프런트엔드(3000)가 모두 떠 있어야 함
```

`apps/web/e2e/`의 6개 테스트가 Phase 2-4 지시문의 시나리오 A~F(정보조사/이슈분석/후보선정/분류수정/출처관리/권한검증)를 그대로 코드화한 것이다. GitHub Actions `e2e-full-stack` 잡은 PostgreSQL+합성 데이터로 동일한 테스트를 매 푸시마다 실행한다.

## CI (GitHub Actions)

`.github/workflows/ci.yml`이 매 push·PR마다 4개 잡을 실행한다: `backend-sqlite`(기존 pytest), `backend-postgres`(PostgreSQL 서비스 컨테이너+Alembic 마이그레이션+동일 pytest 재실행), `frontend-build`(Next.js 프로덕션 빌드), `e2e-full-stack`(PostgreSQL+합성 데이터+실제 FastAPI·Next.js 기동+Playwright 브라우저 테스트). 이 작업 환경에 Docker/PostgreSQL이 없어 로컬에서 못 하는 통합검증을 이 CI가 대신한다 — 단, CI 통과가 "로컬 환경에서도 실행 가능"을 의미하지는 않는다(Docker Compose는 여전히 사용자 환경에서 처음 실행·검증이 필요).

## 운영 계정 만들기

`app.seed`는 로컬 개발·테스트 전용이며 전부 가상 더미 계정이다. 실제 운영 서버에서 쓸 최초 관리자 계정은 아래로 직접 만든다(비밀번호를 코드나 터미널 인자로 넘기지 않는다):

```bash
python -m app.create_admin --email admin@실제도메인 --name "관리자 이름" --prompt-password
# 또는 --prompt-password를 빼면 무작위 비밀번호를 생성해 1회만 출력한다
```

이후 다른 참여 연구원 계정은 관리자가 로그인해 API로 생성하거나(현재는 가입 화면 미구현, Phase 4 예정), 같은 스크립트를 반복 실행해 추가한다.

## 보안 관련 알려진 사항 / 운영 전 점검 목록

- 인증은 httpOnly 쿠키(`access_token`) + 더블 서브밋 CSRF 쿠키(`csrf_token`) 조합을 쓴다. 토큰을 브라우저 JS(localStorage 등)에 저장하지 않는다.
- 로그인 5회 연속 실패 시 15분 잠금(계정 단위, DB에 기록되므로 다중 프로세스 배포에도 유효). `app/core/config.py`의 `max_failed_login_attempts`/`login_lockout_minutes`로 조정.
- `PATCH /auth/password`로 로그인한 사용자가 직접 비밀번호를 바꿀 수 있다.
- `docker-compose.yml`/`.env.example`의 Postgres 비밀번호(`tnp_password`)는 로컬 개발용 예시 값이다 — 운영에서는 반드시 강력한 값으로 교체.
- `cookie_secure`(기본 `false`)는 운영에서 HTTPS를 쓴다면 반드시 `true`로 바꿔야 쿠키에 `Secure` 속성이 붙는다.
- `evidence_claims`, `editions`, `manuscripts` 등 11개 테이블은 스키마만 존재하고 API는 아직 없다(Phase 2 후속~3).
- 운영 환경에서 여러 API 프로세스/서버로 수평 확장할 경우 로그인 잠금 외의 요청 단위 rate limiting(Nginx/Cloudflare 등 인프라 레벨)을 별도로 두는 것을 권장한다 — 현재 구현은 로그인 엔드포인트 전용이다.

## 공개 시연(`/preview/`) 만들기·확인

`preview/index.html`은 서버 없이 동작하는 읽기 전용 화면이며 `preview/data/snapshot.json`만 읽는다(로그인·저장·파일 생성은 로컬 통합 사이트에서만 동작). 스냅샷은 수집 시점의 복사본이므로 갱신하려면 다시 만든다.

```bash
cd apps/api
PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe -m app.export_public_snapshot ../../preview/data/snapshot.json
cd ../../preview && python -m http.server 8765   # http://localhost:8765/index.html
```
