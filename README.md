# TNP AI Platform — weekly-ict-demo

이 저장소는 두 개의 서로 다른 산출물을 담고 있다.

1. **`index.html`** — IITP 제안 발표용 공개 시연 데모. GitHub Pages로 그대로 서빙되며 **이번 작업으로 전혀 손대지 않았다**.
2. **`apps/`** — 실제 운영을 목표로 새로 짓기 시작한 Next.js + FastAPI + PostgreSQL 시스템. 아래는 이 시스템에 대한 안내다.

> 전체 설계 배경·DB 스키마·로드맵은 [`docs/PLATFORM_PLAN.md`](./docs/PLATFORM_PLAN.md), 기존 데모 기능 전수 감사는 [`docs/FEATURE_AUDIT.md`](./docs/FEATURE_AUDIT.md) 참고.

## 지금 상태 — 무엇이 실제로 되고, 무엇이 안 되는지

| 항목 | 상태 |
|---|---|
| FastAPI 백엔드(인증 + 후보주제 CRUD + 검토/승인) | **구현·실행·테스트 완료** — `pytest` 29개 전부 통과, 실제 서버 기동 후 curl로 end-to-end 확인함 |
| 인증 보안(httpOnly 쿠키, CSRF, 로그인 잠금, 비밀번호 변경) | **구현·테스트 완료** — 쿠키/CSRF/계정잠금/비밀번호변경 각각 자동 테스트로 확인(아래 "보안 관련 알려진 사항" 참고) |
| PostgreSQL 스키마(14개 테이블 + 로그인 잠금·출처/문서 메타데이터 확장) + Alembic 마이그레이션 3건 | **구현 완료** — SQLite로 실제 `alembic upgrade head` 성공 확인(Postgres 자체는 이 작업 환경에 설치되어 있지 않아 미설치 상태로 검증) |
| 로컬 개발용 더미 계정 시드 | **구현·실행 완료** — 전부 가상 인물, 비밀번호는 실행마다 무작위 생성 |
| Next.js 프런트(로그인 + 후보주제 목록/상세/의견작성) | **코드 작성 완료, 실행·빌드 미검증** — 이 작업 환경에 Node.js/npm이 설치되어 있지 않아 `npm install`/`npm run dev`를 돌려보지 못했다 |
| Docker Compose(db+api+web) | **설정 파일 작성 완료, 미검증** — 이 작업 환경에 Docker가 설치되어 있지 않다 |
| 다방식(RSS+API) 수집 엔진 — ICT 9대 분야 전체 | **구현·실행 완료 — 9대 분야 전부 최소 1곳(총 10개 출처)에서 실시간 수집 성공 확인**, 255건 실제 DB 저장·재수집 중복방지·404 오류분류까지 라이브 검증. 상세는 `docs/PLATFORM_PLAN.md` §7 참고 |
| 문서별 원문 전문 추출(HTML+PDF) + ICT 분야 자동분류(출처 고정분야와 분리) + 실무 활용가치 판정 + 핵심내용 구조화 + AI 연동(공급자 미설정 시 규칙기반 폴백) | **구현·실행 완료 — 기존 255건 전체 재처리, 전문추출 215건 성공, 35건이 출처 고정분야와 다르게 재분류됨(Phase 2-1 결함 수정 확인)**. 실데이터 검증 중 발견한 실제 결함 3건(단위 오매칭, 기술표준 오분류, PDF 핵심내용 추출 오류)도 전부 수정. AI는 키 미보유로 실호출 미검증(규칙 기반으로만 동작 확인). 상세는 `docs/PLATFORM_PLAN.md` §8 참고 |
| HTML 파싱 수집기(Federal Register 외), 분야별 2곳 이상 확보, 이슈 클러스터링(`issue_clusters`), 실제 AI 모델 호출, 연구원이 분석 결과를 보는 웹 화면, 원고·발간 워크플로, 실제 메일 발송 | **미구현** (Phase 2 후속~3, `docs/PLATFORM_PLAN.md`의 로드맵 참고) |

**직접 실행해서 확인해야 하는 것: Next.js 빌드/구동과 Docker Compose 전체 스택.** 아래 절차대로 진행하고, 안 되는 부분이 있으면 알려달라.

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

마지막 실행 결과: **64 passed**. 테스트는 SQLite 인메모리 DB를 사용한다(운영은 Postgres). 수집 엔진 테스트는 네트워크 호출을 모킹해 로직(신규/중복/개정판/실패/반복실패시 needs_review)만 검증하고, 인증 보안 테스트는 쿠키·CSRF·계정잠금·비밀번호변경을 각각 확인한다. Phase 2-2 분류·전문추출·가치판정·구조화·AI연동 테스트는 `tests/test_classification.py`, `test_extraction.py`, `test_value_assessment.py`, `test_structured_extract.py`, `test_ai_service.py`, `test_documents_api.py` 참고. 실제 네트워크를 통한 라이브 검증 결과는 `docs/PLATFORM_PLAN.md` §7-2, §8-3·8-4 참고.

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

## 프런트엔드 단독 실행 — 사용자 환경에서 처음 실행·검증 필요

```bash
cd apps/web
npm install
npm run dev
```

`NEXT_PUBLIC_API_URL`(기본 `http://localhost:8000`)을 바꾸려면 `.env.local`에 설정.

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
