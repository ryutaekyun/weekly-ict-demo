# TNP AI Platform — weekly-ict-demo

이 저장소는 두 개의 서로 다른 산출물을 담고 있다.

1. **`index.html`** — IITP 제안 발표용 공개 시연 데모. GitHub Pages로 그대로 서빙되며 **이번 작업으로 전혀 손대지 않았다**.
2. **`apps/`** — 실제 운영을 목표로 새로 짓기 시작한 Next.js + FastAPI + PostgreSQL 시스템. 아래는 이 시스템에 대한 안내다.

> 전체 설계 배경·DB 스키마·로드맵은 [`docs/PLATFORM_PLAN.md`](./docs/PLATFORM_PLAN.md), 기존 데모 기능 전수 감사는 [`docs/FEATURE_AUDIT.md`](./docs/FEATURE_AUDIT.md) 참고.

## 지금 상태 — 무엇이 실제로 되고, 무엇이 안 되는지

| 항목 | 상태 |
|---|---|
| FastAPI 백엔드(인증 + 후보주제 CRUD + 검토/승인) | **구현·실행·테스트 완료** — `pytest` 13개 전부 통과, 실제 서버 기동 후 curl로 end-to-end 확인함 |
| PostgreSQL 스키마(14개 테이블) + Alembic 마이그레이션 | **구현 완료** — SQLite로 실제 `alembic upgrade head` 성공 확인(Postgres 자체는 이 작업 환경에 설치되어 있지 않아 미설치 상태로 검증) |
| 사용자 시드(실제 11명 연구원 + 역할) | **구현·실행 완료** |
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
python -m app.seed              # 임시 비밀번호: ChangeMe!2026 (즉시 변경할 것)
uvicorn app.main:app --reload
```

- `GET http://localhost:8000/health` → `{"status":"ok"}`
- `POST http://localhost:8000/auth/login` with `{"email": "heo.seonyang@tenopa.co.kr", "password": "ChangeMe!2026"}`

### 테스트

```bash
cd apps/api
PYTHONPATH=. pytest -v
```

마지막 실행 결과: **16 passed**. 테스트는 SQLite 인메모리 DB를 사용한다(운영은 Postgres). 수집 엔진 테스트는 `fetch_raw_feed`를 모킹해 실제 네트워크 없이 로직(신규/중복/실패)만 검증한다.

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

## 알려진 단순화(운영 전 반드시 바꿀 것)

- JWT를 `localStorage`에 저장한다(Phase 1 최소 구현). 운영 전환 시 httpOnly 쿠키로 교체 필요 — `docs/PLATFORM_PLAN.md` §4 참고.
- 시드 사용자 비밀번호(`ChangeMe!2026`)는 전원 동일한 임시값이다. 최초 로그인 후 반드시 변경.
- `evidence_claims`, `editions`, `manuscripts` 등 11개 테이블은 스키마만 존재하고 API는 아직 없다(Phase 2~3).
