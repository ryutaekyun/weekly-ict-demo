# TNP AI Platform — weekly-ict-demo

이 저장소는 두 개의 서로 다른 산출물을 담고 있다.

1. **`index.html`** — IITP 제안 발표용 공개 시연 데모. GitHub Pages로 그대로 서빙되며 **이번 작업으로 전혀 손대지 않았다**.
2. **`apps/`** — 실제 운영을 목표로 새로 짓기 시작한 Next.js + FastAPI + PostgreSQL 시스템. 아래는 이 시스템에 대한 안내다.

> 전체 설계 배경·DB 스키마·로드맵은 [`docs/PLATFORM_PLAN.md`](./docs/PLATFORM_PLAN.md), 기존 데모 기능 전수 감사는 [`docs/FEATURE_AUDIT.md`](./docs/FEATURE_AUDIT.md) 참고.

## 지금 상태 — 무엇이 실제로 되고, 무엇이 안 되는지

| 항목 | 상태 |
|---|---|
| FastAPI 백엔드(인증 + 후보주제 CRUD + 검토/승인) | **구현·실행·테스트 완료** — `pytest` 23개 전부 통과, 실제 서버 기동 후 curl로 end-to-end 확인함 |
| 인증 보안(httpOnly 쿠키, CSRF, 로그인 잠금, 비밀번호 변경) | **구현·테스트 완료** — 쿠키/CSRF/계정잠금/비밀번호변경 각각 자동 테스트로 확인(아래 "보안 관련 알려진 사항" 참고) |
| PostgreSQL 스키마(14개 테이블 + 로그인 잠금 컬럼) + Alembic 마이그레이션 2건 | **구현 완료** — SQLite로 실제 `alembic upgrade head` 성공 확인(Postgres 자체는 이 작업 환경에 설치되어 있지 않아 미설치 상태로 검증) |
| 로컬 개발용 더미 계정 시드 | **구현·실행 완료** — 전부 가상 인물, 비밀번호는 실행마다 무작위 생성 |
| Next.js 프런트(로그인 + 후보주제 목록/상세/의견작성) | **코드 작성 완료, 실행·빌드 미검증** — 이 작업 환경에 Node.js/npm이 설치되어 있지 않아 `npm install`/`npm run dev`를 돌려보지 못했다 |
| Docker Compose(db+api+web) | **설정 파일 작성 완료, 미검증** — 이 작업 환경에 Docker가 설치되어 있지 않다 |
| RSS 수집 엔진(출처 등록/실행/이력) + 중복감지 | **구현·실행 완료 — 실제 출처 3곳(arXiv cs.AI, NIST News, W3C News)에서 실시간 수집 성공 확인**. 나머지 6개 분야는 검증된 출처를 아직 못 찾아 비워둠 |
| 분야 간 중복 클러스터링(`issue_clusters`), 원고·발간 워크플로, 실제 메일 발송 | **미구현** (Phase 2 후속~3, `docs/PLATFORM_PLAN.md`의 로드맵 참고) |

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

마지막 실행 결과: **23 passed**. 테스트는 SQLite 인메모리 DB를 사용한다(운영은 Postgres). 수집 엔진 테스트는 `fetch_raw_feed`를 모킹해 실제 네트워크 없이 로직(신규/중복/실패)만 검증하고, 인증 보안 테스트는 쿠키·CSRF·계정잠금·비밀번호변경을 각각 확인한다.

### 출처 수집 실행

```bash
python -m app.seed_sources   # 검증된 공식 출처 3곳 등록
# 이후 POST /sources/{id}/collect 호출(관리자/승인자/검토자 권한)
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
