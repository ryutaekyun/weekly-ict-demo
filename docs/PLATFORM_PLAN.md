# TNP AI Platform — 실제 운영 시스템 전환 계획

## 0. 이 문서의 목적과 범위

`index.html`(GitHub Pages 공개 데모)은 TIPA/IITP 제안 발표용 시연 화면으로 **그대로 유지**한다. 이 문서는 그 옆에 새로 추가하는 `apps/web`(Next.js) + `apps/api`(FastAPI) + PostgreSQL 기반의 **실제 운영 시스템**을 어떻게 짓는지 정의한다.

**중요한 환경 제약(투명성 고지):** 이 작업을 수행한 환경에는 Docker, Node.js/npm, PostgreSQL이 설치되어 있지 않고 Python만 설치되어 있다. 따라서:
- 백엔드(FastAPI + SQLAlchemy + Alembic + pytest)는 **실제로 설치·실행·테스트까지 완료**하고 그 결과를 그대로 보고한다.
- 프런트엔드(Next.js)와 Docker Compose 구성은 **코드/설정 파일로 작성**하지만 이 환경에서 `npm install` / `docker compose up`을 **실행·검증하지 못했다**. README에 사용자 쪽에서 실행·검증하는 절차를 명시한다. 이는 원칙 "구현하지 않은 기능을 작동한다고 표시하지 말 것"에 따른 것이다.

---

## 1. 현재 데모 기능 감사 (실제 동작 vs 시연용 정적 데이터 vs 미구현)

파일 전체 1,872줄, repo에는 `index.html`과 `.git`만 존재(별도 js/css/package.json 없음). **네트워크 호출(`fetch`/`XMLHttpRequest`/`axios`/`WebSocket`) 0건, `localStorage`/`sessionStorage` 0건** — 모든 "데이터"는 하드코딩이거나 새로고침하면 사라지는 메모리상 DOM 상태다.

### `window.__*` 함수 전수 조사

| 함수 | 실제 동작 |
|---|---|
| `__goSection` / `__goView` | 순수 클라이언트 라우팅(class 토글). 데이터 로딩 없음 |
| `__registerIssue` | 가장 실질적인 기능 — 클릭 시 `topicTable`+`reviewTable`에 실제로 새 행 삽입, 탭 카운트·KPI 갱신, 새 화면으로 이동. 단 새로고침 시 소실, `cardGrid`/수집통계/분석리포트에는 반영 안 됨 |
| `__openCommentEditor`/`__submitComment` | 검토의견 실제 DOM 추가·검토일 갱신. 저장 안 됨 |
| `__openApprovalEditor`/`__submitApproval` | 상태 pill·탭 카운트 실제 변경. view-1/6의 동일 항목엔 미반영, 저장 안 됨 |
| `__sendConfirm` | 버튼 텍스트만 바꾸는 완전 코스메틱 — 실제 발송/등록 없음 |
| `__scrollToId` | 스크롤 이동만 |

### 화면별 요약 (전체 표는 하단 "화면 기능 감사 원본" 참고)

- **실데이터 연동이 필요한(=이미 일부 로직은 있는) 기능**: 섹션/뷰 전환, 분야·상태 필터 탭(`wireFilter`), 후보 등록, 검토의견 작성, 최종승인 pill, 캘린더/파이프라인 상세 패널(단, 데이터 소스가 하드코딩된 JS 객체).
- **시연용 정적 데이터(화면 대부분)**: 모든 KPI 숫자, 차트/SVG, 발간관리·메일진·품질관리·출처관리·분석리포트·설정의 테이블 거의 전부.
- **클릭 가능하나 미작동(장식용 버튼)**: 검색창, 알림벨, 계정 드롭다운, 상세화면의 "검토완료"/"원문보기", 카드보기 10/11장의 "자세히 보기"(1번만 동작), 날짜선택기, 엑셀/PDF 다운로드, 파일 업로드, 계정추가, 알림/연동 토글, 직급 select(onchange 없음).
- **완전 미구현**: 로그인/인증, 데이터 영속성, 백엔드 API, 실제 출처 수집·크롤링 엔진, AI 변경감지 엔진, 실제 메일 발송 인프라, 역할별 접근 제어.

전체 표는 [`docs/FEATURE_AUDIT.md`](./FEATURE_AUDIT.md) 참고. 이 감사는 Phase 1 범위를 "후보주제(candidates) 1건을 뼈대부터 끝까지 실제 DB로" 잡은 근거다 — 데모에서 가장 완성도 높은 상호작용(`__registerIssue`/검토의견/승인)이 전부 candidates 주변에 몰려 있고, 지금 빠진 한 가지(영속성)만 해결하면 되기 때문이다.

---

## 2. 목표 아키텍처

```
weekly-ict-demo/                  (기존 repo, 그대로 유지)
├── index.html                    (기존 공개 데모 — 손대지 않음)
├── apps/
│   ├── api/                      (FastAPI 백엔드)
│   │   ├── app/
│   │   │   ├── core/             (config, security/JWT, db session)
│   │   │   ├── models/           (SQLAlchemy ORM — 13+1개 테이블)
│   │   │   ├── schemas/          (Pydantic 요청/응답 스키마)
│   │   │   ├── api/              (라우터: auth, candidates, sources, ...)
│   │   │   └── main.py
│   │   ├── alembic/               (DB 마이그레이션)
│   │   ├── tests/                 (pytest)
│   │   └── requirements.txt
│   └── web/                      (Next.js 프런트엔드 — 기존 디자인 토큰 재사용)
│       ├── app/                   (App Router: /login, /candidates, ...)
│       ├── components/            (Panel, Pill, KpiTile, DataTable — 기존 CSS 변수 그대로 포팅)
│       └── package.json
├── infra/
│   └── docker-compose.yml        (postgres + api + web)
└── docs/
    └── PLATFORM_PLAN.md          (본 문서)
```

**왜 같은 저장소, 새 폴더인가:** 기존 UI를 "무단 삭제·대규모 변경하지 말 것"이라는 원칙과, GitHub Pages가 지금처럼 루트 `index.html`을 계속 서빙해야 한다는 요구를 동시에 만족하는 가장 안전한 방법이다. 새 시스템은 Pages가 아니라 로컬/사내 서버에서 Docker로 띄운다.

**공개 데모 vs 내부 시스템 분리(요구사항 #4 대응):** 새 Next.js 앱은 **전 구간 로그인 필수**로 설계한다(비로그인 공개 라우트 없음). 실제 연구원 이름·내부 일정·검토의견은 인증된 사용자만 본다. 기존 GitHub Pages `index.html`은 지금처럼 익명화된 시연 데이터만 유지한다 — 즉 "공개 데모"와 "내부 운영 시스템"은 물리적으로 분리된 두 개의 산출물이다.

---

## 3. 데이터베이스 스키마 (PostgreSQL)

사용자가 지정한 13개 테이블에, 인증을 위해 **`users`** 테이블을 추가한다(요구사항 #4의 사용자 인증·역할 구현에 필수이며 원래 목록에 없었음).

| 테이블 | 핵심 컬럼 | 관계 |
|---|---|---|
| **users** | id, email, password_hash, display_name, role(enum: researcher/reviewer/approver/admin), job_title, is_active, created_at | — |
| **sources** | id, name, org_name, field_code(9대분야 enum), url, source_type(rss/api/html), reliability_tier, is_active, created_at | — |
| **collection_runs** | id, source_id FK, started_at, finished_at, status(success/partial/failed), items_found, items_new, items_duplicate, error_message, retry_count | source_id→sources |
| **source_documents** | id, source_id FK, collection_run_id FK, title, origin_url(UNIQUE), published_at, collected_at, raw_text, content_hash, status(collected/parsed/duplicate/failed), duplicate_of_id(self FK) | source_id→sources, collection_run_id→collection_runs |
| **issue_clusters** | id, title, field_code, first_seen_at, representative_document_id FK, status(active/merged/archived) | representative_document_id→source_documents |
| **evidence_claims** | id, candidate_id FK, claim_text, source_document_id FK, source_url, verified_by_user_id FK, verified_at, verification_status(unverified/confirmed/disputed/corrected), note | candidate_id→candidates, source_document_id→source_documents, verified_by_user_id→users |
| **candidates** | id, issue_cluster_id FK, field_code, title, summary, source_document_id FK, announced_date, source_org, recommended_reason, status(rec/review/hold/final/rejected), created_by_user_id FK, created_at, updated_at | issue_cluster_id→issue_clusters, created_by_user_id→users |
| **candidate_reviews** | id, candidate_id FK, reviewer_user_id FK, comment_text, is_final_approval(bool), decided_status(nullable), created_at | candidate_id→candidates, reviewer_user_id→users |
| **editions** | id, publication_type(weekly_report/card_news/biweekly_brief/tech_trend), edition_label, target_date, status, created_at | — |
| **manuscripts** | id, edition_id FK, candidate_id FK(nullable), author_user_id FK, title, body, manuscript_type, status(draft/review/final), created_at, updated_at | edition_id→editions, candidate_id→candidates, author_user_id→users |
| **manuscript_versions** | id, manuscript_id FK, version_no, body_snapshot, edited_by_user_id FK, change_note, created_at | manuscript_id→manuscripts, edited_by_user_id→users |
| **approvals** | id, approvable_type(candidate/manuscript/publication), approvable_id, approver_user_id FK, decision(approved/rejected/hold), comment, decided_at | approver_user_id→users (polymorphic — approvable_id는 FK 제약 없이 approvable_type으로 구분) |
| **publications** | id, edition_id FK, channel(mail/itfind/web), published_at, published_by_user_id FK, recipient_count, external_url, status | edition_id→editions, published_by_user_id→users |
| **audit_logs** | id, actor_user_id FK(nullable=system), action, entity_type, entity_id, detail_json, created_at | actor_user_id→users |

모든 테이블: `id`는 UUID(서버 생성), 타임스탬프는 `timestamptz`. `source_documents.origin_url`에 UNIQUE 제약 + `content_hash`로 **중복 기사 감지**(요구사항 #7)의 1차 방어선을 둔다.

---

## 4. 인증·권한

- JWT 기반(FastAPI + `python-jose` + `passlib[bcrypt]`), 쿠키 저장(httpOnly) + Next.js 미들웨어로 비로그인 접근 차단.
- 역할 4단계: `researcher`(검토의견 작성) · `reviewer`(검토 담당 지정) · `approver`(최종 승인 — IITP 제출 전 PM 역할) · `admin`(사용자/출처 관리).
- 역할별 접근 제어는 FastAPI `Depends`로 라우터 단에서 검사(`require_role(["approver","admin"])` 형태).

---

## 5. 단계별 로드맵

### Phase 0 — 기초 구조 ✅ 완료
리포지토리 구조, `docker-compose.yml`, FastAPI 스켈레톤(헬스체크), SQLAlchemy 모델 14종 전체, Alembic 초기 마이그레이션, `.env.example`, 기본 README.

### Phase 1 — 핵심 CRUD 수직 슬라이스 ✅ 완료(백엔드), 🟡 프런트는 코드만 작성·실행 미검증
요구사항 #5(후보주제 CRUD) 전체를 실제 DB로 구현하고 자동 테스트로 검증하는 데 집중한다:
- `users` 시드 + JWT 로그인/로그아웃 API
- `candidates` 전체 CRUD + 검색/필터(분야, 상태) + 상태변경 API
- `candidate_reviews` 작성 API(일반 검토의견 + `is_final_approval` 승인 코멘트)
- pytest로 위 전부에 대한 성공/실패 케이스 작성 및 실행
- Next.js 최소 화면: 로그인 페이지 + 후보주제 목록/상세 페이지(기존 데모의 `topicTable`/`reviewTable` 디자인 토큰 그대로 재사용) — **이 프런트는 이 환경에서 직접 빌드·구동 검증을 못 했음을 명시**

### Phase 2 — 수집 파이프라인 ✅ 핵심 엔진 완료(출처 3/9개 검증), 나머지 진행 중
RSS 수집 엔진(`app/services/collection.py`)을 구현해 **실제 공인 출처 3곳(arXiv cs.AI·NIST News·W3C News — 전부 이 세션에서 직접 curl로 HTTP 200·정상 RSS 응답 확인)**을 대상으로 실시간 수집을 실행해 검증했다. `POST /sources/{id}/collect`를 실제로 호출해 arXiv에서 신규 논문 50건을 수집, origin_url 기준 재수집 시 50건 전부 중복 처리, 존재하지 않는 URL에 대해서는 404를 실패로 정확히 기록(재시도 카운트 증가)하는 것까지 **실제 네트워크 호출로 확인**했다.

나머지 6개 분야(디지털사회혁신·방송전파위성·SW자율주행·콘텐츠미디어·반도체양자·ICT융합기술)는 **검증된 공식 출처를 아직 찾지 못해 의도적으로 비워뒀다** — 추측 URL을 절대 등록하지 않는다는 원칙에 따른 것이며, 담당자가 실제 출처를 확인해 `app/seed_sources.py`에 추가하면 된다. `issue_clusters`를 이용한 분야 간 중복 클러스터링은 아직 미구현(Phase 2 후속).

### Phase 3 — 원고·발간 워크플로 (다음 승인 후 진행)
`editions`/`manuscripts`/`manuscript_versions`/`approvals`/`publications` — 원고 집필·교정 이력, IITP 승인 게이트, 실제 발송 연동은 **사람의 명시적 승인 없이는 외부 발송 불가**하도록 설계(요구사항의 "발간 승인 및 외부 발송은 사람의 명시적 승인 요구" 반영).

### Phase 4 — 전체 UI 이관
나머지 메뉴(발간관리/메일진·ITFind/품질·분야 관리/출처관리/분석리포트/설정)를 Next.js로 1:1 이관.

---

## 5-1. 보안 긴급 수정(Phase 2 재개 전 선행 조치, 2026-10-22)

공개 저장소의 `apps/api/app/seed.py`에 실제 참여 연구원 11명의 이름·추정 사내 이메일·공통 임시 비밀번호가 평문으로 커밋되어 있던 문제를 수정했다.
- `app/seed.py`: 전부 가상 더미 계정(`dev-*@example.com`)으로 교체, 비밀번호는 실행마다 무작위 생성해 콘솔에 1회만 출력(코드에 저장하지 않음)
- `app/create_admin.py`(신규): 운영 환경 최초 관리자 계정을 안전하게 만드는 CLI(비밀번호는 숨김 입력 또는 1회성 무작위 생성)
- 인증을 `localStorage` 토큰 → httpOnly 쿠키(+더블 서브밋 CSRF 쿠키)로 전환, 로그인 5회 실패 시 계정 잠금(DB 기록이라 다중 프로세스에도 유효), `PATCH /auth/password` 추가
- README/문서에 남아 있던 실제 이메일·비밀번호 예시 전부 제거
- **주의**: 이 정보는 이미 공개 저장소의 과거 커밋 히스토리에 포함되어 있다. 히스토리를 강제로 재작성(rebase/filter-branch 등)하거나 저장소 공개 설정을 바꾸는 작업은 사용자 승인 없이 실행하지 않았다 — 필요 여부는 사용자가 결정할 사안.
- **공개 데모(index.html) 실명 표시 — 사용자 확인 완료**: 제안서 발표용으로 의도된 선택이었음을 확인받아 그대로 유지한다(변경하지 않음).

## 6. 검증 결과 (실제 실행함)

- `pip install -r requirements.txt` 성공 (passlib/bcrypt 버전 호환 이슈 1건 발견 → `bcrypt==4.0.1` 고정으로 해결)
- `alembic revision --autogenerate` → 14개 테이블 전부 정상 감지, `alembic upgrade head` → SQLite에 실제 적용 성공
- `python -m app.seed` → 실제 연구원 11명 실제 역할로 삽입 확인
- `uvicorn app.main:app` 실제 기동 후 `curl`로 `/health`, `/auth/login`, `POST /candidates`, `GET /candidates` 전부 실제 HTTP 응답으로 확인(TestClient가 아닌 실제 네트워크 요청)
- `pytest -v` → **23 passed**(2026-10-22 보안 수정 반영 후 기준 — 로그인 성공/실패, 권한 없는 생성 차단, 분야·검색 필터, 일반 검토의견, 비승인자의 최종승인 시도 차단(403), 승인자의 최종승인 성공, PATCH로 직접 final 전환 시도 차단, 삭제 권한 제어, RSS 수집 신규/중복/실패 3건, httpOnly 쿠키·CSRF 차단/통과·로그인 잠금·비밀번호 변경·로그아웃 7건)

미검증 항목(이 환경에 Docker/Node.js가 없음): `docker compose up`, `npm install`/`npm run dev`/`npm run build`. 사용자 환경에서 README의 절차대로 실행 후 결과를 알려주면 바로 이어서 고치겠다.

---

## 7. Phase 2-1 — ICT 9대 분야 실제 수집 확대 (2026-10-22, 사용자 품질 재검증 반영)

최초 구현 직후 사용자가 "단순 등록이 아니라 실제 저장 여부", "원문 링크가 개별 문서로 연결되는가", "보고서 집필에 쓸 수 있는 자료인가" 3가지를 짚어 재검증을 요청했고, 실제로 점검해 보니 **3건의 실제 결함**이 나와 전부 고쳤다. 아래 7-0이 그 내용이고, 7-1·7-2는 수정 반영 후 최종 상태다.

### 7-0. 품질 재검증에서 발견·수정한 결함

1. **API 응답에 원문 요약이 아예 빠져 있었음** — DB(`source_documents.raw_text`)에는 arXiv 초록·Federal Register abstract가 제대로(수백~2천자 이상) 저장돼 있었는데, `SourceDocumentOut` 스키마에 `raw_text` 필드를 넣지 않아 API로는 조회가 안 됐다. 스키마에 추가해 수정 — "제목만 가져온다"는 우려는 데이터 자체의 문제가 아니라 API 노출 누락이었다.
2. **문서 목록 정렬이 사실상 임의순이었음** — `GET /sources/{id}/documents`가 `collected_at desc`로 정렬했는데, 한 번의 수집에서 저장되는 문서들은 `collected_at`이 밀리초 단위로만 다르거나 같아서 "최신순"이 보장되지 않았다(실제로 2018~2024년 문서가 앞쪽에 뜨는 현상 발생). `published_at desc`로 정렬 기준을 바꿔 수정.
3. **출처 3곳(NTIA/FCC/NHTSA)이 기관 전체 피드라 관리성 공지가 다수 섞여 있었음** — 필터 없이 기관 전체를 긁으면 Privacy Act 기록공고·OMB 서류수집 공고 같은 행정 잡음이 결과 상당수를 차지했다. 아래처럼 좁혔다:
   - NTIA: 필터 없음 → `term=broadband`(광대역 프로그램·디지털포용 관련 건으로 한정)
   - FCC: 필터 없음 → `type=RULE,PROPOSED RULE`(확정/입법예고 규칙만, 공지성 문서 제외)
   - NHTSA: 필터 없음 → `term="autonomous vehicle"`(일반 차량안전 규정 제외, 자율주행 관련 건만)
   - ICT 융합기술의 NSF "Convergence Accelerator" 출처는 재점검 결과 응답이 전부 행정공고뿐이라 **완전히 폐기**하고, 실제 내용이 확인된 OSTP(백악관 과학기술정책실)로 교체.

수정 후 재검증(2026-10-22, 동일 세션 재실행): 10개 출처 전부 2025~2026년 최신 문서, 문서당 요약 150~2,500자 확보. 품질 기준을 만족하는지 아래 7-0-1에서 3가지 질문별로 직접 답한다.

### 7-0-1. 사용자가 지정한 3가지 기준에 대한 답

**① 9개 분야 모두 수집 성공 — 실제 저장까지 확인했는가?**
예. 10개 출처 전부 `status=success`로 실행 완료, `source_documents` 테이블을 SQLite로 직접 SELECT해 분야별 실제 행 수를 확인했다(API 응답만 보고 판단하지 않음). 재수집 시 중복 0건 삽입도 실측 확인(아래 7-2 하단).

**② 원문 링크가 실제 개별 문서로 연결되는가?**
예. 브라우저로 직접 열어 확인했다 — FCC 문서(`.../upper-c-band-398-42-ghz-...`)는 기관·조치유형·발효일·담당자 연락처까지 담긴 실제 규칙 전문 페이지였고, BIS 반도체 문서도 동일하게 확인됨. arXiv·NIST·W3C는 각 페이지의 `<title>`이 저장된 제목과 정확히 일치함을 curl로 확인했다. 전부 기관 홈페이지나 검색결과 화면이 아니라 문서 하나하나의 고유 URL(Federal Register는 `/documents/YYYY/MM/DD/문서ID-slug`, arXiv는 `/abs/논문ID`)이다.

**③ 추후 보고서 집필에 쓸 수 있는 자료인가?**
수정 전에는 아니었다 — 위 7-0의 3번 문제 그대로였다면 "Sunshine Act 회의 공고", "OMB 서류수집 공고" 같은 무관한 행정문서가 샘플 상단을 차지했을 것이다. 수정 후에는 분야별로 실질적인 정책·규제·연구 문서(예: FCC의 상위 C-밴드 주파수 확대, BIS의 폴리실리콘 비축 규제, NHTSA의 Zoox 자율주행차 임시면제 승인, OSTP의 첨단제조 국가전략 RFI)가 상위에 오르고, 각 문서에 150~2,500자의 실제 요약(summary/abstract)이 함께 저장돼 있어 원고 집필 시 바로 참고할 수 있는 수준이다. 다만 NTIA는 광대역 프로그램 관련이어도 일부(약 40%)가 "정보수집 활동 공고" 형태의 행정문서라 — 이 출처 하나는 품질이 완전하지 않음을 밝혀둔다(7-4 참고).

### 7-1. 분야별 출처 확보 현황 (최종)

9대 분야 전부 **최소 1곳 이상 실제 작동 확인**. "분야별 2곳 이상" 목표는 인공지능·데이터 1개 분야만 달성했고, 나머지 8개 분야는 1곳씩이다(사유는 7-4 참고).

| 분야 | 출처명 | 수집 방식 | 필터 | 실제 수집 성공 | 신규 수집(이번 실행) |
|---|---|---|---|---|---|
| 인공지능·데이터 | arXiv cs.AI | RSS | — | ✅ | 50건 |
| 인공지능·데이터 | Federal Register — NIST×AI | API | agency=NIST, term="artificial intelligence" | ✅ | 20건 |
| 통신·네트워크 | W3C News | RSS | — | ✅ | 25건 |
| 보안·블록체인 | NIST News | RSS | — | ✅ | 40건 |
| 디지털사회혁신 | Federal Register — NTIA | API | agency=NTIA, term="broadband" | ✅ | 20건 |
| 방송·전파·위성 | Federal Register — FCC | API | agency=FCC, type=RULE/PRORULE | ✅ | 20건 |
| SW·자율주행 | Federal Register — NHTSA | API | agency=NHTSA, term="autonomous vehicle" | ✅ | 20건 |
| 콘텐츠·미디어 | Federal Register — US Copyright Office | API | agency=Copyright Office | ✅ | 20건 |
| 반도체·양자 | Federal Register — BIS×반도체 | API | agency=BIS, term="semiconductor" | ✅ | 20건 |
| ICT 융합기술 | Federal Register — OSTP | API | agency=OSTP | ✅ | 20건 |

전체 URL은 `apps/api/app/seed_sources.py`에 있다.

### 7-2. 실제 수집 사례 (2026-10-22 품질 수정 후 재실행, 제목·요약·발표일·URL 전부 라이브로 재확인)

| 분야 | 원문 제목 | 발표일 | 원문 URL | 요약 길이 |
|---|---|---|---|---|
| 인공지능·데이터 | The More the Better? A Comparison of Single- and Multi-Agent LLM Setups on a Financial Review Task | 2026-10-22 | arxiv.org/abs/2610.27488 | 1,459자 |
| 인공지능·데이터(FR) | NIST Artificial Intelligence Consortium | 2026-05-29 | federalregister.gov/documents/2026/05/29/2026-10779-... | 2,487자 |
| 통신·네트워크 | W3C and the State of the Web in the AI Era | 2026-10-21 | w3.org/news/2026/w3c-and-the-state-of-the-web-in-the-ai-era | 355자 |
| 보안·블록체인 | New Chip-Based 'Tape Measure' for Light Could Revolutionize Mobile Timekeeping | 2026-10-16 | nist.gov/news-events/news/2026/10/new-chip-based-tape-measure-light-... | 109자 |
| 디지털사회혁신 | NTIA Listening Session on Screen-Based Instruction in K-12 Schools | 2026-08-27 | federalregister.gov/documents/2026/08/27/2026-17435-... | 786자 |
| 방송·전파·위성 | Upper C-Band (3.98-4.2 GHz); Expanding Flexible Use of the 3.7 to 4.2 GHz Band | 2026-10-19 | federalregister.gov/documents/2026/10/19/2026-21324-... | 337자(브라우저로 전문 확인) |
| SW·자율주행 | Zoox — Grant of Temporary Exemption ... for an Automated Driving System-Equipped Vehicle | 2026-07-31 | federalregister.gov/documents/2026/07/31/2026-15485-... | 1,351자 |
| 콘텐츠·미디어 | Music Streaming Fraud | 2026-10-07 | federalregister.gov/documents/2026/10/07/2026-20537-... | 164자 |
| 반도체·양자 | Measures To Restrict Stockpiling of Polysilicon and Polysilicon Derivatives Under Proclamation 11052 | 2026-09-24 | federalregister.gov/documents/2026/09/24/2026-19537-... | 1,043자(브라우저로 전문 확인) |
| ICT 융합기술 | United States Global Change Research Program; Availability for Public Comment... (NCA5) | 2026-08-25 | federalregister.gov/documents/2026/08/25/2026-17289-... | 380자 |

라이브 실행 결과 전체: 10개 출처 모두 `status: success`, 총 254건 실제 DB 저장(`source_documents` 테이블 직접 SELECT로 확인, API 응답만으로 판단하지 않음). 재수집 시 arXiv 50건 전부 `items_duplicate`로 분류되어 신규 삽입 0건(중복방지 재확인). 존재하지 않는 URL로 만든 테스트 출처는 실제 404를 받아 `status: failed`, `error_type: http_4xx`로 정확히 기록됨(성공으로 집계되지 않음).

### 7-3. 개발 결과

**신규/확장 기능**
- 다방식 수집 디스패처(`app/services/collection.py`): `source_type`(rss/api/html)에 따라 분기, API는 `api_provider` 레지스트리로 공급자별 파서 선택(현재 `federal_register` 1종 구현)
- Federal Register(federalregister.gov) API 수집기 — 공식 API, 키 불필요
- 출처별 메타데이터 확장: `country_code`, `is_primary_source`, `api_provider`, `needs_review`, `consecutive_failures`, `last_attempted_at`, `last_successful_collection_at`
- 문서별 메타데이터 확장: `language`, `country_code`, `document_type`(정책/법령/논문/표준/보도자료/뉴스 등), `field_code`(문서의 실제 분야 — 출처의 고정 분야와 분리), `collection_method`, `attachment_url`, `document_updated_at`, `is_peer_reviewed`, `requires_primary_source_check`, `previous_version_id`
- 오류 유형 분류(`CollectionErrorType`): http_4xx/429/5xx, timeout, connection_error, parse_error 등 — `collection_runs.error_type`에 기록
- "동일 URL·내용 변경" 개정판 추적: `previous_version_id`로 연결된 새 버전 행 생성(완전 중복과는 다른 개념으로 분리, `items_updated` 카운트 별도 집계)
- 출처 반복 실패 시 자동 비활성화 대신 `needs_review` 플래그(3회 연속 실패 시 설정, `is_active`는 그대로 유지)
- `GET /sources/{id}`(문서수·최근 실행상태 포함), `PATCH /sources/{id}`(관리자 전용 — 활성화/비활성화/검토플래그 해제 등) 신규 API
- (품질 재검증 중 수정) `SourceDocumentOut` 응답에 `raw_text`(요약) 필드 추가 — 누락돼 있어 API로는 요약을 받을 수 없었음
- (품질 재검증 중 수정) `GET /sources/{id}/documents` 정렬 기준을 `collected_at desc` → `published_at desc`로 변경 — 전자는 동일 배치 삽입 시 사실상 임의 순서였음

**데이터베이스 구조 변경** — 마이그레이션 2건(`0f8878ee2c82` 외, 상세는 alembic/versions 참고)
- `source_documents.origin_url`의 UNIQUE 제약 제거(개정판 다중 저장을 위함), 비유니크 인덱스로 대체
- 위에 나열한 신규 컬럼 전체 추가, `SourceDocumentStatus`에 `UPDATED` 값 추가

**테스트**: 신규 6건 추가(Federal Register 파서 정상 변환, 개정판 추적, 교차출처 중복, 반복실패시 needs_review, 관리자 전용 PATCH 권한, 출처 상세 통계) — 전체 **29/29 통과**. 라이브 네트워크 검증은 7-2 참고(HTTP 200만으로 성공 처리하지 않고 실제 파싱·DB 저장 건수까지 확인).

**아직 미구현**
- HTML 파싱 수집기(우선순위 3순위) — 이번 라운드에 로봇 정책을 만족하면서 충분히 단순·안정적인 실제 대상을 찾지 못해 구현을 보류했다. 예시 없이 코드만 작성하지 않기로 한 원칙에 따른 것이다.
- 원문 전문 추출(현재는 요약/abstract 수준만 `raw_text`에 저장) 및 AI 자동 분류(`field_code`가 아직 출처의 고정 분야를 그대로 상속) — Phase 2-2 범위
- 이슈 클러스터링(`issue_clusters` 연동) — Phase 2-3 범위
- 출처 관리 화면(웹 UI) — 이번 단계는 백엔드 API까지만, Next.js 화면 연동은 후속 단계

**추후 보완 필요**
- 분야별 2곳 이상 확보 목표 미달(7곳 분야가 1곳뿐) — 추가 리서치 필요
- 전부 영문 해외 출처뿐 — 일본 총무성·경제산업성, 중국 공업정보화부, 대만 디지털발전부 등 RFP가 명시한 아시아권 기관은 이번 라운드에 실제 접속 가능한 공식 API/RSS를 확인하지 못해 보류(개별 사이트 로그인/캡차 없는 공개 엔드포인트 존재 여부를 더 조사해야 함)
- NTIA(디지털사회혁신) 출처는 `term=broadband`로 좁혀도 상위 결과의 약 40%가 "정보수집 활동 공고" 류의 행정문서다 — 완전히 만족스러운 수준은 아니며 대체·보강 출처가 필요하다
- Federal Register 문서는 `raw_text`에 공식 abstract/summary만 저장되고 본문 전문은 아직 가져오지 않는다 — 전문이 필요하면 Phase 2-2에서 각 문서 페이지 자체를 파싱해야 한다

### 7-4. 미확보 분야·사유 및 대체 방안

"분야별 2곳 이상" 미달 7개 분야 공통 사유: 이번 라운드는 "이미 존재가 확인된 API/RSS"만 쓴다는 원칙에 따라 Federal Register라는 단일 공급자(미국) 중심으로 빠르게 9/9 분야 커버리지를 확보하는 데 집중했다. 그 결과 다양성(특히 비(非)미국·아시아권 1차 출처)이 부족하다. 다음 라운드에서 우선 조사할 후보: 일본 총무성(www.soumu.go.jp) 보도발표 RSS 유무, 경제산업성(www.meti.go.jp) 공지사항 피드, 3GPP/O-RAN ALLIANCE의 공개 문서 목록 API 또는 다운로드 페이지, EU Digital Strategy(digital-strategy.ec.europa.eu) 뉴스 섹션의 RSS 유무 — 전부 다음 라운드에서 실제 접속해 확인한 뒤에만 등록한다.

## 8. Phase 2-2 — 원문 전문 추출·ICT 분야 자동 분류·실무 활용성 검증 (2026-10-22)

Phase 2-1의 알려진 한계 두 가지(출처의 고정 분야를 문서 분야로 그대로 쓰는 문제, 요약만 있고 원문 전문이 없는 문제)를 해결하는 단계다. 완료 기준은 수집 건수가 아니라 "실제 원문을 확보하고 적절한 분야로 분류해 근거 있는 분석자료로 쓸 수 있는가"이므로, 아래 전부를 기존 254~255건 실데이터(삭제하지 않고 그대로 재처리)로 검증했다.

### 8-1. 신규 아키텍처

**신규 테이블 6개** (마이그레이션 `980507d2ffa1`, autogenerate로 생성 후 검수):
- `document_classifications` — 문서별 "현재" 분류(주 분야/연관 분야/관련성/신뢰도/판정방식/근거). `SourceDocument.field_code`(Phase 2-1 때 출처 분야를 그대로 복사한 값)는 하위호환을 위해 그대로 두고 건드리지 않았다 — 이 테이블의 `primary_field_code`가 Phase 2-2 이후의 공식 분야다.
- `document_classification_history` — 분류가 바뀔 때마다(최초 자동분류 포함) 한 행씩 남는 이력. 누가(연구원 ID 또는 시스템) 언제 무엇을 바꿨는지 추적.
- `document_full_texts` — 원문 전문. 요약(`SourceDocument.raw_text`)과 분리 저장. 추출상태/방식/글자수/위치설명/실패사유/재추출시 변경여부를 함께 저장.
- `document_value_assessments` — 실무 활용가치 판정(우선검토/일반검토/관련성낮음/추가확인필요) + 판정기준 6개 충족여부(JSON) + 근거 인용문.
- `document_structured_extracts` — 핵심내용 구조화(핵심내용/배경목적/정책기술변화/핵심수치/핵심일정/관계기관/쟁점/예상영향(사실·AI분석 구분)/추가확인사항/원문출처인용).
- `ai_analysis_runs` — AI(또는 규칙 기반) 분석 1회 호출 기록(공급자/모델/버전/상태/오류/재시도/처리시각) — 문서 분석 전용이 아니라 향후 보고서 집필·쟁점분석에도 재사용할 범용 로그 테이블로 설계.

**신규 서비스 모듈** (`apps/api/app/services/`):
- `field_taxonomy.py` — ICT 9대 분야의 정의·포함주제·제외주제·경계사례·키워드를 분야당 1곳에서 관리. 키워드만으로 분류 기준을 구성하지 말라는 지시에 따라 정의/포함/제외/경계사례를 1차 자료로, 키워드는 규칙 기반 분류기와 AI 프롬프트가 함께 참조하는 2차 자료로 둠.
- `classification.py` — 문서별 자동 분류. AI 공급자가 설정돼 있으면 AI를 먼저 시도하고, 미설정이거나 호출 실패 시 **반드시** 규칙 기반(키워드 가중합)으로 대체하며 `method=rule_based`로 저장(AI 분석으로 표시 금지). 연구원 수정용 override 함수 포함.
- `extraction.py` — HTML 본문 추출(BeautifulSoup, `<article>`/`<main>` 우선 → 최다 텍스트 블록 휴리스틱, robots.txt 사전 확인) + PDF 텍스트 추출(pypdf, 페이지당 평균 추출 글자수가 낮으면 스캔본으로 간주해 SUCCESS로 표시하지 않음) + arXiv 초록페이지→전문PDF URL 자동 유도.
- `value_assessment.py` — 6개 기준(①분야관련성 ②정책산업중요성 ③단순행정공고 여부 ④내용충분성 ⑤시의성 ⑥출처신뢰성) 규칙 기반 판정. 시의성(최근7일/30일/90일/과거)은 저장하지 않고 **조회 시점마다 다시 계산**한다(저장하면 시간이 지나며 값이 거짓이 되므로).
- `structured_extract.py` — 규칙 기반 모드에서는 원문에서 직접 패턴매칭 가능한 항목(핵심수치, 핵심일정, 관계기관)만 채우고, 해석이 필요한 항목(쟁점, 예상영향)은 "AI 미설정으로 생성하지 않음"으로 비워 둔다.
- `ai_service.py` — 공급자 중립 AI 연동(Anthropic/OpenAI). 서버 환경변수(`AI_PROVIDER`/`AI_MODEL`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`)로만 설정하며, 미설정이면 `get_ai_provider()`가 `None`을 반환해 호출부가 규칙 기반으로 대체하도록 강제한다. 긴 원문 분할(`chunk_text`), AI 응답 JSON 파싱(`extract_json_object`) 유틸 포함.
- `pipeline.py` — 문서 1건에 대해 전문추출→분류→가치판정→구조화를 순서대로 실행하는 오케스트레이터. 관련성이 "낮음/보류"인 문서는 구조화 단계를 건너뛴다(무관한 자료를 억지로 보고서용 자료처럼 구조화하지 않기 위함).

**신규 API** (`/documents`, `apps/api/app/api/documents.py`):
- `POST /documents/{id}/process` — 파이프라인 전체 실행(관리자/승인자/검토자 권한)
- `GET /documents/{id}/analysis` — 분류+전문상태(본문 제외)+가치판정(시의성 포함)+구조화+AI호출이력 통합 조회
- `GET /documents/{id}/full-text` — 원문 전문 본문 조회(별도 엔드포인트로 분리해 목록 조회 응답이 무거워지지 않게 함)
- `PATCH /documents/{id}/classification`, `PATCH /documents/{id}/value-assessment` — **연구원이 AI/규칙 기반 결과를 직접 수정**(사유 필수 입력 가능, 이력에 자동 기록)

### 8-2. 실데이터 검증에서 발견·수정한 실제 결함 3건

255건 전체 재처리 후 분야별 표본을 직접 원문과 대조하다가 발견한 것들이다 — 전부 발견 당일 수정하고 재처리까지 재실행해 반영했다.

1. **차량안전 문서의 '0.5g 감속도' 단위가 '5G/6G' 통신기술로 오매칭됨.** NHTSA의 자율주행차 안전기준 문서(`New Car Assessment Program ... Advanced Driver Assistance Systems`)가 통신·네트워크(NET)로 분류됐는데, 실제로는 "5g"/"6g" 키워드가 "0.5g"/"0.6g"(제동 감속도 단위, g-force) 표기와 정규식 단어경계에서 충돌한 것이었다 — 해당 문서에만 "5g"가 65회, "6g"가 27회 "매칭"됐지만 전부 감속도였다. 수정: 모호한 단독 토큰 "5g"/"6g"를 "5g network"/"6g technology" 같은 구체적인 복합어로 교체.
2. **W3C 기술표준(WCAG 등)이 '접근성'이라는 단어 하나만으로 디지털사회혁신(SOC, 사회정책 분야)으로 오분류됨.** W3C의 "WCAG 2.2/2.1 프랑스어 번역 공지", "EPUB Accessibility 1.2 Explainer" 2건이 실제로는 웹 기술표준 공지인데 SOC로 분류됐다. 수정: SOC의 "accessibility/접근성" 키워드 가중치를 낮추고, NET에 "wcag", "web content accessibility guidelines" 등 표준명 키워드를 추가해 기술표준 자체는 NET로, 장애인 접근성 "정책"은 SOC로 갈리게 함.
3. **연방관보(Federal Register) PDF의 인쇄판 특성상, 핵심내용 추출이 엉뚱한 직전 문서의 꼬리 문단을 가져옴.** Federal Register는 하나의 문서 PDF도 인쇄판 지면을 그대로 자른 것이라, 문서 시작 지점에 직전의 무관한 다른 고시의 마지막 문단이 섞여 들어오는 경우가 있다(예: NTIA의 "광대역 프로그램 지속가능성 간담회" 문서 PDF 1페이지 앞부분에 수산자원관리청의 "참치 어획량" 고시 꼬리말이 포함됨). 분류 점수는 전체 텍스트를 다 보므로 영향이 적었지만, 구조화 단계의 "핵심내용"이 이 무관한 꼬리 문단을 그대로 가져가는 문제가 있었다. 수정: 연방관보 문서는 예외 없이 "SUMMARY:" 필드로 그 문서 자신의 요지를 명시하므로, 본문에서 "SUMMARY:"를 찾아 그 뒤부터를 핵심내용으로 추출하도록 변경(`structured_extract.py::_first_paragraphs`). 수정 후 실제로 재확인: 위 NTIA 문서의 `key_content`가 올바르게 "NTIA의 OICG가 BEAD/디지털형평성 등 보조금 프로그램을 운영하며..."로 바뀜.

이 3건 모두 `apps/api/tests/test_classification.py`·`test_structured_extract.py`에 재발 방지 회귀 테스트로 추가했다.

### 8-3. 실데이터 재처리 결과 (255건 전체, 2026-10-22)

| 항목 | 결과 |
|---|---|
| 처리 대상 | 255건(DUPLICATE 제외, 기존 문서 그대로 — 삭제 없음) |
| 처리 성공 | 255건 / 실패 0건 |
| 원문 전문 추출 성공 | 215건(HTML 25건 + PDF 190건), 평균 73,855자, 최대 1,443,958자(arXiv 388p 논문) |
| 전문 추출 시도 안 함(robots.txt 차단) | 40건 — 전부 NIST News(nist.gov가 `/news-events/` 경로를 robots.txt로 크롤링 금지, 직접 확인함) → 요약만으로 분류·판정 진행 |
| 분류: 9대 분야 매칭 | 161건 |
| 분류: 관련성낮음/분류보류 | 94건 — 억지로 9대 분야에 끼워 넣지 않음 |
| 출처 고정분야와 다르게 재분류된 문서 | 35건 — Phase 2-1의 "출처=문서 분야" 가정이 실제로 틀렸음을 보여줌 |
| 가치판정: 우선검토 | 21건 |
| 가치판정: 일반검토 | 134건 |
| 가치판정: 관련성낮음 | 97건 |
| 가치판정: 추가확인필요 | 3건 |

**분야별 매칭 건수**: AI 65 · SW 20 · CONTENT 20 · SEMI 18 · BCAST 16 · NET 13 · SEC 8 · SOC 1 · **CONV 0**.

**CONV(ICT융합기술) 분야는 이번 수집분에서 미충족으로 보고한다.** 유일한 출처인 OSTP Federal Register 피드의 실제 문서들(기후연구계획 공람, 나노기술 이니셔티브 회의공고, 성과평가위원회 명단 등)을 직접 대조해 보니 스마트시티/스마트제조/탄소중립 등 CONV의 정의(포함주제)와 실질적으로 맞는 문서가 하나도 없었다 — 분류 보류로 정직하게 남겨 두었고, 무관한 자료를 억지로 CONV에 끼워 넣지 않았다. CONV를 실제로 채우려면 스마트시티/탄소중립을 직접 다루는 새 출처(예: DOE 스마트그리드, EPA 탄소중립 정책 피드)가 추가로 필요하다 — 후속 과제로 남긴다.

### 8-4. 분야별 표본검증(자동판정 vs 원문 대조, 일부 발췌)

| 분야 | 문서(발췌) | 자동판정 | 원문 대조 결과 |
|---|---|---|---|
| 인공지능·데이터 | arXiv "Physical AI: Concepts, Techniques, and Challenges" | ai(신뢰도 0.99) | 적절 — 실제 물리 AI 서베이 논문, 키워드도 본문과 일치 |
| 통신·네트워크 | W3C "Group Note: WCAG Evaluation Methodology 2.0" | net(0.78) | 적절(수정 후) — W3C 웹 기술표준 공지, 수정 전엔 SOC로 오분류됐었음(8-2 참고) |
| 방송·전파·위성 | FCC "Unleashing Unlicensed Spectrum for Direct-to-Device" | bcast(0.99) | 적절 — 위성-단말 직접통신용 비면허 주파수 개방 규칙, 15페이지 전문 확보 |
| SW·자율주행 | BIS "Securing the ICT and Services Supply Chain: Connected Vehicles" | sw(0.99) | 적절 — 출처는 반도체(semi) 고정분야였으나 실제 내용은 커넥티드카 SW/공급망 규제라 sw로 재분류됨(의도한 동작) |
| 보안·블록체인 | Federal Register "RFI on Modernizing the National Vulnerability Database in the Age of AI" | sec(0.96) | 적절 — 출처는 AI 고정분야(NIST×AI 쿼리)였으나 실제 주제는 NVD(국가취약점데이터베이스) 운영 개선이라 sec로 재분류됨(의도한 동작) |
| 콘텐츠·미디어 | US Copyright Office "Music Streaming Fraud" | content(0.99), 우선검토 | 적절 — 스트리밍 사기 관련 저작권청 공식 조사·권고 문서 |
| 반도체·양자 | BIS "Additions and Modifications to the Entity List; Removals From the VEU Program" | semi(0.99) | 적절 — 반도체 수출통제 대상기관(Entity List) 조정 |
| 디지털사회혁신 | NTIA "State Digital Equity Capacity Grant Program" | soc(0.69) | 적절 — 디지털 형평성 보조금 프로그램, SOC 정의(디지털 격차 해소)와 정확히 일치. 다만 이 분야는 이 1건이 유일한 매칭(위 8-3 참고) |
| ICT 융합기술 | (매칭 없음) | — | 미충족 — 8-3 참고 |

이 표에서 "적절"로 판단한 기준은 ① 문서 제목·전문 내용이 분야 정의(포함주제)와 실제로 맞는가, ② 신뢰도·매칭근거(판정근거 문장)가 실제 본문 내용과 일치하는가 두 가지를 직접 원문(또는 전문 추출 결과)과 대조해 확인한 것이다. 반도체·보안 분야 2건은 "출처의 고정 분야와 다른 분야로 재분류"된 사례를 일부러 골라, Phase 2-1의 핵심 결함이 실제로 고쳐졌음을 보였다.

### 8-5. AI 연동 현황 — 실제로 호출했는가

**아니다.** 이 작업 환경에는 `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`가 설정돼 있지 않다(세션 자체의 `ANTHROPIC_BASE_URL`은 이 Claude Code 세션 전용 내부 설정이라 재사용하지 않았다 — 별도 외부 서비스에 무단 전용하지 않기 위함). 따라서 이번 255건은 전부 `method=rule_based`로 저장됐고, 분류·가치판정·구조화 응답 어디에도 "AI 분석 완료"라는 표시는 없다.

대신 `ai_service.py`의 공급자 연동 코드(Anthropic/OpenAI HTTP 호출, JSON 파싱, 청크분할) 자체는 `tests/test_ai_service.py`로 키 없이도 기계적으로 검증했다(공급자 미설정 시 `None` 반환, 공급자 설정+키 있을 때 프로바이더 인스턴스 생성, 청크 분할 경계, JSON 추출 성공/실패 케이스). 운영 환경에서 `.env`에 `AI_PROVIDER=anthropic`과 `ANTHROPIC_API_KEY`만 넣으면 코드 변경 없이 실제 AI 분류·구조화가 즉시 켜지도록 설계했다(`.env.example` 참고).

### 8-6. 개발·테스트 결과

- **신규 파일**: 모델 5개, 서비스 7개, API 라우터 1개, 스키마 1개, 마이그레이션 1개, 운영스크립트 2개(`reprocess_documents.py`, `run_all_collections.py`)
- **테스트**: 신규 35건 추가(분류 7건, 전문추출 7건, 가치판정 6건, AI서비스 7건, 구조화 2건, API 6건) — 기존 29건 포함 **전체 64/64 통과**
- **기존 기능 회귀 없음**: `GET /sources/{id}/documents` 등 Phase 2-1 API 응답 형식 그대로 유지(회귀 테스트로 확인)
- **미구현/미검증**: 실제 AI 모델 호출(키 미보유로 라이브 검증 불가, 메커니즘만 검증), 이슈 클러스터링(Phase 2-3), 연구원이 실제 웹사이트에서 이 분석 결과를 보는 화면(Next.js 미연동, Phase 2-4)
- **다음 단계 필요사항**: CONV 분야 보강 출처 확보, AI 공급자 키 확보 시 실제 분류 품질 재검증, 분류 보류(94건) 중 실제로 9대 분야에 해당하지만 키워드가 부족해 놓친 건 없는지 추가 표본검증

## 9. Phase 2-3 — AI 핵심 이슈·쟁점 분석 및 후보주제 추천 엔진 (2026-10-22)

Phase 2-2에서 분류·전문추출까지 끝난 161건(관련성=matched)을 "문서 단위"가 아니라 "이슈 단위"로 통합하고, 신규/후속 변화·쟁점·논쟁·후보주제를 생성하는 단계다. 완료 기준은 "이슈 그룹을 만드는 것"이 아니라 "여러 자료를 근거로 변화·쟁점을 구분하고 연구원이 검토할 수 있는 후보주제를 내놓는 것"이므로, 전부 161건 실데이터로 검증했다.

### 9-1. 신규 아키텍처

**신규 테이블 7개**(마이그레이션 `02ddbcdbccc2`):
- `issue_cluster_documents` — 클러스터↔문서 소속(문서당 1개 클러스터만, 멤버십 유형: 대표/후속/동일사건 중복보도)
- `issue_cluster_membership_history` — 자동배정·병합·분리 이력
- `issue_timeline_events` — 신규이슈/추가발표/실질변경/후속조치/변화없음/비교자료부족 6종으로 구분한 변화 이력
- `issue_analyses` — 클러스터 단위 핵심내용·쟁점(기술/정책/산업우려)·국가비교·국내시사점·논쟁상태(클러스터당 1건)
- `issue_dispute_points` — 상반된 주장 1건씩(논쟁이 없으면 행 자체를 만들지 않음)
- `candidate_scoring_config` — 후보추천 가중치(싱글턴, 관리자 PATCH 가능)
- `candidate_recommendation_scores` — 후보주제별 5개 기준 점수·근거·평가보류 사유
- (기존 `issue_clusters`에 `summary`/`last_activity_at`/`review_status`/`created_by_method` 컬럼 추가)

**신규 서비스**(`apps/api/app/services/`): `issue_clustering.py`(통합 판정), `issue_timeline.py`(변화감지), `issue_analysis.py`(핵심내용·쟁점·논쟁), `candidate_recommendation.py`(가중점수 추천), `issue_pipeline.py`(오케스트레이션).

**신규 API**(`/issues`): `GET /issues`(분야·기간 검색), `GET /issues/{id}`(통합상세), `POST /issues/cluster/{document_id}`, `POST /issues/{id}/analyze`, `POST /issues/{id}/recommend`, `PATCH /issues/{id}/merge`, `POST /issues/split`, `GET·PATCH /issues/scoring/config`(가중치, 관리자 전용).

**통합 판정 설계**(실데이터 관찰 기반): 이 데이터셋은 뉴스매체가 같은 사건을 반복 보도하는 구조가 아니라 연방관보 공식 규제문서가 대부분이다. 그래서 RIN/Docket 번호 일치를 "동일 사건"의 1차(강한) 신호로, 제목 유사도+발표일 근접을 2차(약한) 신호로 썼다 — "키워드가 같다는 이유만으로 통합하지 않는다"는 지시를 지키기 위해서다. RIN/Docket 같은 강한 신호는 **문서별 분야 분류와 무관하게 전역에서** 비교한다(분류 오차로 같은 규제가 다른 분야로 갈려도 통합은 돼야 하므로). 반대로 한쪽이라도 서로 다른 RIN/Docket을 갖고 있으면(=이미 별개 조치임이 확인됨) 제목이 아무리 비슷해도 약한 신호 매칭을 적용하지 않는다.

### 9-2. 실데이터 검증에서 발견·수정한 실제 결함 7건

1. **세션 `autoflush=False` 설정 때문에 방금 만든 소속 레코드를 바로 못 읽음** — 클러스터 배정 직후 같은 트랜잭션에서 조회하면 `NoResultFound`. `_add_membership`에 명시적 `db.flush()` 추가.
2. **동일 RIN인데 분야 분류가 달라 클러스터링이 안 됨** — FMVSS 305a 규제(RIN 2127-AM43) 2건이 각각 bcast/sw로 분류돼, 분야 범위로 좁힌 검색에서 서로를 못 찾았다. 강한 신호(RIN/Docket) 검색은 분야 제한 없이 전역으로 수정.
3. **서로 다른 RIN인데 제목이 비슷해 묶일 뻔함** — "지시사항이 명시적으로 경고한 실수"를 테스트로 재현해 확인. 양쪽 모두 RIN/Docket이 확인되는데 다르면(=이미 별개임이 확인됨) 제목 유사도 매칭 자체를 건너뛰도록 수정.
4. **"as opposed to"(비교 관용구)가 논쟁 신호로 오매칭됨** — "opposed" 단독 키워드가 "A as opposed to B"(A와 달리/대조적으로) 구문과 자주 충돌했다(15개 표본 중 4~5건이 이 패턴). "as _ opposed"/"opposed to" 전후 문맥을 보고 관용구는 제외하도록 수정.
5. **재분석 시 사라진 논쟁이 이전 행으로 남아있음** — 오탐 수정 후 재분석하면 `dispute_status=NO_DISPUTES_CONFIRMED`인데 이전 실행의 `IssueDisputePoint` 행이 그대로 남는 불일치가 있었다. 새 결과가 비어 있어도 항상 먼저 지우고 다시 채우도록 수정.
6. **"허브 문서"가 서로 다른 두 규제조치를 섞는데 자동 확정됨** — "Public Briefing on Changes to Advanced Computing..." 1건이 서로 다른 RIN(0694-AJ74, AJ77) 2건을 함께 언급해, 두 개의 무관한 BIS 수출통제 조치가 한 클러스터로 묶였다. 매칭된 클러스터가 이번 식별자 외에 *다른* 식별자도 갖고 있으면 `review_status=needs_review`로 돌리도록 수정.
7. **(6의 수정 중 발견) 같은 RIN인데 Docket 번호가 달라 정상 사례까지 허브로 오판**했다 — NHTSA가 동일 규제(RIN 2127-AM43)의 NPRM 단계(Docket NHTSA-2024-0012)와 Final Rule 단계(Docket NHTSA-2024-0091)에 서로 다른 Docket 번호를 매기는 것은 정상 관행이었다. RIN으로 이미 매칭됐으면 Docket 차이는 허브 판단 근거로 쓰지 않도록(매칭에 쓰인 식별자 종류만 비교) 수정.
8. **(부록) SQL `NULL != x`는 거짓으로 취급돼 중복확인에서 일부 후보가 빠짐** — 후보주제 참신성 점수 계산 시 `issue_cluster_id IS NULL`인 기존 후보(클러스터 없이 등록된 것)가 중복검사 대상에서 누락됐다. `OR issue_cluster_id IS NULL` 조건 추가.

8건 전부 `tests/test_issue_clustering.py`·`test_issue_analysis.py`·`test_candidate_recommendation.py`에 재발 방지 회귀 테스트로 추가했다.

### 9-3. 실데이터 재처리 결과(161건 전체, 2026-10-22)

| 항목 | 결과 |
|---|---|
| 클러스터링 대상(관련성=matched) | 161건 |
| 생성된 이슈 클러스터 | 143건(단일문서 130 + 복수문서 13) |
| 복수 문서 통합 | 13개 클러스터에 18건 합류(동일 RIN/Docket 7건, 제목유사도 약한신호 11건) |
| 통합 상태: 확정(confirmed) | 135건 |
| 통합 상태: 검토대기(needs_review) | 8건 — 전부 약한 신호 매칭이거나 허브문서 의심 사례, 자동 확정하지 않음 |
| 타임라인: 신규이슈 | 143건 |
| 타임라인: 후속조치(강한 신호) | 7건 |
| 타임라인: 비교자료부족(약한 신호 — 추측하지 않음) | 11건 |
| 논쟁분석: 확인된 대립 없음 | 110건 |
| 논쟁분석: 논쟁 발견(연구원 확인 필요로 표시) | 33건(실제 행 36건) |
| 후보주제 추천 | 142건(관련성낮음 자료만 있는 1개 클러스터는 추천 제외) |
| 국내 산업 연관성 "평가 보류" | 142/142건 — 전부(아래 9-5 참고) |

**복수 문서 클러스터 13건 전체**:

| 클러스터(대표문서) | 문서 수 | 통합 근거 | 상태 |
|---|---|---|---|
| FMVSS No. 305a Electric-Powered Vehicles | 2 | 동일 RIN 2127-AM43(NPRM→Final) | 확정 |
| FMVSS Occupant Crash Protection | 2 | 동일 RIN 2127-AL37 | 확정 |
| FMVSS Automatic Emergency Braking | 2 | 동일 RIN/Docket | 확정 |
| Public Briefing on Changes to Advanced Computing... | 3 | 설명회 1건이 서로 다른 RIN(AJ74/AJ77) 2건과 연결 | **검토대기(허브문서 의심)** |
| National Artificial Intelligence Advisory Committee | 6 | 동일 제목의 반복 회의공고(제목유사도 1.00) | **검토대기(반복공지 — 실질 변화 불명)** |
| Revisions to the Entity List 외 5건 | 각 2 | 제목유사도(약한 신호) | 검토대기 또는 확정(사안별) |

### 9-4. 분야별·유형별 표본검증(실제 검증 수행, 최소 사례 전부 실데이터)

| 검증 항목 | 실제 사례 |
|---|---|
| ① 서로 다른 문서가 동일 사건 | FMVSS 305a NPRM(2024-04-15)·Final(2024-12-20), 동일 RIN 2127-AM43 → 타임라인 `substantive_change`로 정확히 분류 |
| ② 유사 키워드, 별개 사건(통합 금지 검증) | "Revisions to the Entity List"(2024-08-27) vs "Additions and Revisions to the Entity List"(2025-09-16) — 제목유사도 0.75로 높지만 13개월 간격+RIN 불일치로 **통합되지 않음**(의도대로 동작) |
| ③ 후속 조치·변경 | 위 FMVSS 305a 사례 — "NPRM 단계가 Final로 전환됨" 설명 자동 생성 |
| ④ 원문 1건뿐인 독립 이슈 | 130건(예: "Music Streaming Fraud") — 비교 대상이 없어 전부 `new_issue`로 정직하게 처리 |
| ⑤ 논쟁이 확인되지 않는 이슈 | 110건 — `dispute_status=no_disputes_confirmed`로 명시(없음을 없다고 말함) |
| ⑥ 근거자료 부족 이슈 | 모든 클러스터의 "국내 산업 연관성"(142/142) — 미국 중심 데이터라 근거 없이 임의 작성하지 않고 전부 평가보류 |
| ⑦ ICT 분야 분류가 보류된 문서 | 94건(Phase 2-2 분류보류) — 애초에 클러스터링 대상에서 제외(관련성=matched만 처리), 무관한 자료로 이슈를 억지로 만들지 않음 |
| 허브 문서(모호 사례) | "Public Briefing..." 1건이 서로 다른 BIS 수출통제 조치 2건과 연결 — 자동 확정하지 않고 검토대기 |

### 9-5. AI 연동 및 "추정 금지" 원칙 준수 현황

Phase 2-2와 동일하게 이 환경에는 AI API 키가 없어 **실제 AI 모델 호출은 전혀 없었다** — 142건 추천·143건 분석 전부 `method=rule_based`다. `issue_analysis.py`/`candidate_recommendation.py`의 AI 연동 코드(프롬프트 구성, JSON 파싱, `ai_analysis_runs` 기록)는 작성·단위테스트까지만 됐고 라이브 호출은 미검증이다.

규칙 기반 모드에서 "추정 금지" 원칙이 실제로 어떻게 지켜졌는지:
- **국가별 비교**: 데이터가 사실상 미국(Federal Register) 중심이라, 142건 전부 "타국 입장을 임의로 작성하지 않음 — 추가 출처 확보 필요"로 정직하게 기록했다. 다른 나라 입장을 지어내지 않았다.
- **국내(한국) 산업 연관성**: 미국 규제문서만으로는 근거가 없으므로 142/142건 전부 `domestic_has_sufficient_basis=False`로 비워 뒀다 — 가짜 연관성을 만들지 않았다.
- **쟁점 카테고리화(기술/정책/산업우려)**: 해석이 필요한 영역이라 규칙 기반에서는 생성하지 않고 "AI 미설정으로 생성하지 않음"으로 명시했다.
- **논쟁 탐지**: 규칙 기반은 패턴 매칭으로 "한쪽 주장"만 찾아내고, 상대측 주장은 "연구원이 직접 확인 필요"로 남겨 둔다(9-2의 결함 4·5가 바로 이 탐지의 정확도를 다듬은 과정이다).
- **후보주제 추천**: 국내연관성 점수가 없는 142건은 "평가보류"로 두고, 나머지 4개 기준(정책영향/시의성/참신성/분석확장성)만으로 가중치를 재정규화해 총점을 계산했다 — 근거 없는 항목을 0점 처리해 부당하게 감점하지 않았다.

### 9-6. 개발·테스트 결과

- **신규 파일**: 모델 2개+기존 1개 확장, 서비스 5개, API 라우터 1개, 스키마 1개, 마이그레이션 1개, 운영스크립트 1개(`reprocess_issues.py`)
- **테스트**: 신규 25건(클러스터링 6건, 타임라인 4건, 이슈분석 6건, 후보추천 4건, API 5건) — 기존 64건 포함 **전체 89/89 통과**
- **회귀 없음**: 기존 Phase 2-1·2-2 API/테스트 전부 그대로 통과
- **미구현/미검증**: 실제 AI 모델 호출(키 미보유), 연구원이 이슈·후보주제를 보는 웹 화면(Phase 2-4), 이슈 병합·분리 API는 구현했으나 대량 실사용 시나리오는 미검증
- **다음 단계 필요사항**: 허브문서(식별자 2개 이상 걸리는 경우)의 자동 분리 제안 기능, 비영어·비미국 출처 확보 시 실제 국가비교 분석 재검증, AI 키 확보 시 쟁점 카테고리화·논쟁 양측 주장 생성 기능의 실제 품질 검증

## 10. Phase 2-4 — 실제 웹사이트 구현 및 백엔드 통합·운영환경 검증 (2026-10-23)

이전 단계까지는 수집·분류·이슈통합·후보추천이 전부 백엔드(API+스크립트)에서만 동작했고, 연구원이 쓸 웹 화면과 Node.js/PostgreSQL/Docker 실행 환경 자체가 이 작업 환경에 없어 검증하지 못한 상태였다. 이번 단계에서 먼저 **winget으로 Node.js(LTS v24.20.0)를 이 환경에 직접 설치**했고, 그 위에서 Next.js 웹사이트를 실제로 빌드·실행하고 실제 PostgreSQL/Docker 통합은 GitHub Actions CI로 검증했다. "코드 작성 완료"와 "실제 실행 검증"을 구분해 아래에 정리한다.

### 10-1. 환경 제약과 해결

- 이 작업 환경에는 Node.js/npm/Docker/PostgreSQL이 전혀 설치돼 있지 않았다(전부 `command not found`로 직접 확인). Docker Desktop은 Windows에서 WSL2·관리자 권한이 필요해 설치 부담이 크다고 판단해 보류했다.
- `winget install --id OpenJS.NodeJS.LTS -e --scope user`로 Node.js v24.20.0/npm 11.19.0을 사용자 권한으로 설치 성공(관리자 승인·시스템 설정 변경 없음). 이후 Next.js 빌드·실행·브라우저 E2E 테스트까지 전부 이 Node.js로 직접 실행했다.
- PostgreSQL/Docker는 로컬에 설치하지 않고, GitHub Actions의 `postgres:16-alpine` 서비스 컨테이너에서 실제로 기동해 Alembic 마이그레이션과 전체 pytest 스위트를 돌리는 방식으로 검증했다(`.github/workflows/ci.yml`, 10-6 참고).

### 10-2. Next.js 웹사이트 구현

`apps/web`을 기존 스켈레톤(로그인+후보주제 목록/상세)에서 7개 메뉴를 가진 실제 운영 웹사이트로 확장했다. 공개 데모(`index.html`)의 네이비·화이트 디자인 토큰(`--navy`, `--panel`, `.pill`, `.tbtn` 등)을 그대로 재사용하되, 정적 HTML이 아니라 실제 API를 호출하는 React 컴포넌트로 새로 짰다.

- **Next.js 14.2.15 → 16.4.2로 업그레이드**: 설치 직후 `npm audit`에서 Next 14 계열 전체에 해당하는 critical/high 취약점(Windows 원격코드실행 등 다수)이 확인돼, 아직 실행 검증 전이었던 만큼 최신 버전으로 바로 올렸다(React/React-DOM도 19.3.1로 동반 업그레이드). `npm audit` 결과 0 vulnerabilities.
- **신규 화면**: `/dashboard`(통합 대시보드), `/documents`·`/documents/[id]`(ICT 정보 수집 목록·상세), `/issues`·`/issues/[id]`(핵심 이슈 분석 목록·상세), `/sources`(출처·수집 관리), `/settings`(계정·비밀번호 변경). 기존 `/candidates`·`/candidates/[id]`는 필터·점수표·상태변경 기능을 추가해 확장.
- **공용 셸**(`components/AppShell.tsx`): 사이드바 7개 메뉴(보고서 집필·카드뉴스는 "추후 개발"로 비활성 표시) + 상단 검색창 + 로그인 세션 확인(`/auth/me` 401 시 `/login?next=` 리다이렉트) + 로그아웃.
- 날짜는 전부 `Asia/Seoul` 기준 `toLocaleString("ko-KR", {timeZone:"Asia/Seoul"})`로 표시하고, 공개 데모의 2027년 가상 날짜는 가져오지 않았다.

### 10-3. 백엔드 API 보강(프런트엔드가 필요로 했으나 없던 것)

Phase 2-4를 시작하며 기존 OpenAPI 스키마를 점검한 결과, 목록·대시보드 화면에 필요한 핵심 엔드포인트 2종이 아예 없었다 — "화면만 만들고 백엔드는 그대로 둔다"가 아니라 실제로 빠진 부분을 찾아 추가했다.

| 신규 엔드포인트 | 내용 |
|---|---|
| `GET /documents` | 전체 수집자료 검색·필터(분야·국가·자료유형·출처·검토상태·키워드)·서버측 페이지네이션. 분야 필터는 `SourceDocument.field_code`(출처 고정분야)가 아니라 `document_classifications.primary_field_code`를 기준으로 함(지시사항 준수) |
| `GET /documents/{id}` | 목록과 동일한 형태의 단건 메타데이터(상세화면 헤더용) |
| `GET /dashboard/summary` | 대시보드에 필요한 모든 집계(분야별 건수, 추출상태, 이슈·후보 현황 등)를 매 호출마다 실시간 DB 조회로 계산 — 숫자를 프런트엔드에 하드코딩하지 않음 |
| `GET /dashboard/sources-status` | 출처별 최근 수집 성공/실패 현황 |

그 외에도 `CandidateDetailOut`에 `recommendation_score`(가중점수·근거·평가보류 항목)가 빠져 있어 추가했고, `IssueAnalysisOut`/`IssueDisputePointOut` 스키마가 저장된 세부 JSON 필드(핵심쟁점 카테고리·국가비교·국내 R&D영향 등) 대부분을 응답에서 누락하고 있어 화면이 요구하는 수준으로 전부 노출하도록 넓혔다. 신규/확장 API 전부에 대해 `tests/test_documents_list_and_dashboard.py`(6건)·`tests/test_candidate_detail_score.py`(2건) 회귀 테스트를 추가했다.

### 10-4. 실제 실행·브라우저 검증 (로컬, SQLite 백엔드 `dev.db`)

기존 실데이터(255건 수집, 161건 매칭, 143개 이슈 클러스터, 142건 후보주제)가 들어있는 로컬 `dev.db`를 그대로 띄워 실제 브라우저(Claude 내장 브라우저)로 검증했다. 가상 더미 계정(`dev-admin@example.com` 등, `app.seed`로 생성)의 비밀번호를 로컬 테스트용으로 재설정해 로그인했다 — 운영 계정이 아니며 GitHub에는 올리지 않았다.

| 화면 | 실제 API 연결 | DB 조회 | 수정·저장 | 브라우저 검증 | 비고 |
|---|---|---|---|---|---|
| 로그인/로그아웃 | ✅ | ✅ | - | ✅ | httpOnly 쿠키, 세션 유지 확인 |
| 통합 대시보드 | ✅ | ✅ | - | ✅ | 255/161/143/142 등 실제 DB 수치와 화면 수치 일치 확인 |
| ICT 정보 수집(목록) | ✅ | ✅ | - | ✅ | 분야 필터·페이지네이션(255건, 13페이지) 확인 |
| ICT 정보 수집(상세) | ✅ | ✅ | ✅ | ✅ | 분류·실무활용성 수정 → 저장 → **새로고침 후 "연구원 수정됨" 반영 확인**(실제 DB write) |
| 핵심 이슈 분석(목록·상세) | ✅ | ✅ | - | ✅ | 타임라인·쟁점·국가비교·국내연관성 "평가보류" 정상 표시 확인 |
| 후보주제 선정·검토 | ✅ | ✅ | ✅ | ✅ | 가중점수(부분평가점수 포함) 표시, 검토의견 등록 → **새로고침 후 재확인**(실제 DB write) |
| 출처·수집 관리 | ✅ | ✅ | ✅ | ✅ | "수동 수집 실행" 버튼으로 arXiv에 실제 네트워크 호출 — 신규 0·중복 50건 수집 확인 |
| 사용자 및 운영 설정 | ✅ | ✅ | ✅ | 코드 작성 완료, 비밀번호 변경 폼은 브라우저 미실행 | 계정정보 조회는 검증, 변경 자체는 미실행 |

- **권한 검증**: `dev-researcher-1@example.com`(연구원)으로 로그인해 분류수정을 시도하면 FastAPI가 서버 측에서 403을 반환하고 화면에 "이 작업은 admin, approver, reviewer 권한이 필요합니다"가 표시됨을 확인 — 프런트 버튼 숨김이 아니라 **백엔드가 실제로 권한을 강제**한다. 같은 연구원 계정으로 후보주제 검토의견 등록(허용된 작업)은 정상 동작.
- **서버 재시작 후 데이터 유지**: FastAPI 프로세스를 종료 후 재기동, 대시보드를 새로고침해 동일한 수치(255/161/143/142)가 그대로 유지됨을 확인.

### 10-5. 실제 브라우저 E2E 테스트(Playwright)

`apps/web/e2e/`에 Playwright 테스트 6건을 작성해 지시문의 시나리오 A~F를 코드화했고, 로컬에서 실제 Chromium으로 전부 통과시켰다(`npx playwright test`, 6 passed / 16.2초). CI에서는 처음 보는 데이터셋에도 돌아가도록 하드코딩된 UUID 대신 화면에서 실시간으로 찾은 항목을 클릭하는 방식으로 작성했다.

| 시나리오 | 파일 | 결과 |
|---|---|---|
| A. ICT 정보 조사 | `scenario-a-document-browse.spec.ts` | ✅ pass |
| B. 이슈 분석(복수문서) | `scenario-b-issue-analysis.spec.ts` | ✅ pass |
| C. 후보 선정(의견 작성→저장→재확인) | `scenario-c-candidate-review.spec.ts` | ✅ pass |
| D. 분류 수정(저장→새로고침 반영) | `scenario-d-classification-edit.spec.ts` | ✅ pass |
| E. 출처 관리(실제 수동 수집) | `scenario-e-source-management.spec.ts` | ✅ pass |
| F. 권한 검증(연구원 차단/관리자 허용) | `scenario-f-permissions.spec.ts` | ✅ pass |

### 10-6. PostgreSQL·Docker 통합 — GitHub Actions CI로 검증

로컬에 PostgreSQL/Docker가 없어 `docker compose up`은 이번에도 실행하지 못했다. 대신 `.github/workflows/ci.yml`을 새로 만들어 GitHub가 제공하는 Ubuntu 실행환경에서 다음을 **실제로** 실행하도록 구성했다(코드만 작성한 것이 아니라 이 PR의 커밋·푸시 이후 Actions 탭에서 실행 결과를 직접 확인함 — 아래 10-7 참고):

- `backend-sqlite`: 기존 pytest 전체(97건, SQLite)
- `backend-postgres`: `postgres:16-alpine` 서비스 컨테이너 기동 → `alembic upgrade head`로 실제 PostgreSQL에 전체 스키마 마이그레이션 적용 → 동일 pytest 스위트 97건을 **PostgreSQL 연결로 그대로 재실행**(`tests/conftest.py`가 `TEST_DATABASE_URL` 환경변수를 읽도록 수정해, 같은 테스트 코드가 SQLite/PostgreSQL 양쪽에서 돌아가게 함)
- `frontend-build`: `npm ci` + `npm run build`(Next.js 프로덕션 빌드)
- `e2e-full-stack`: PostgreSQL 기동 → 마이그레이션 → `app.seed_ci_fixtures`(외부 네트워크 호출 없이 합성 문서 3건으로 실제 클러스터링·분석·추천 파이프라인을 그대로 실행) → FastAPI(PostgreSQL 연결)·Next.js(프로덕션 빌드) 기동 → Playwright 6건 전부 실행

CI 성공만으로 "실제 웹사이트의 브라우저 동작이 확인됐다"고 주장하지 않기 위해, 10-4·10-5의 로컬 실제 브라우저 검증(실데이터 255건 기준)을 1차 근거로 삼고 CI는 "Docker/PostgreSQL이 없는 이 개발 환경에서 검증하지 못하는 부분을 보완하는 수단"으로만 사용했다.

**CI가 실제로 찾아낸 PostgreSQL 전용 결함**: 첫 CI 실행에서 `backend-postgres` 잡이 실패했다 — `test_issue_timeline.py`의 4개 테스트와 `test_classification.py` 1개 테스트가 `uuid.uuid4()`로 만든 **존재하지 않는** `cluster_id`/`changed_by_user_id`를 그대로 외래키 값으로 썼는데, SQLite는 기본적으로 외래키 제약을 강제하지 않아(별도 `PRAGMA foreign_keys=ON` 없이는) 지금까지 조용히 통과해 왔다. PostgreSQL은 외래키를 실제로 강제해 `ForeignKeyViolation`으로 즉시 걸러냈다. 프로덕션 코드 경로(`run_clustering_for_document` 등)는 항상 실제로 flush된 클러스터 ID를 쓰므로 버그가 아니라 **테스트 픽스처의 허점**이었고, 테스트가 가짜 UUID 대신 실제 `IssueCluster`/`User` 행을 만들어 쓰도록 고쳤다(로직 자체는 변경 없음). 이것이 바로 "SQLite에서 통과한 테스트가 PostgreSQL에서도 통과하는지 검증"하라는 지시사항이 실제로 의도한 효과다.

### 10-7. 실제 데이터 정합성

| 항목 | DB 실제값(2026-10-23) | 대시보드 표시값 |
|---|---|---|
| 전체 수집 문서 | 255 | 255 |
| ICT 분야 매칭 | 161 | 161 |
| 분류 보류 | 94 | 94 |
| 전문 확보 성공 | 215 | 215 |
| 이슈 클러스터 | 143 | 143 |
| 이슈 통합 검토대기 | 8 | 8 |
| 후보주제 | 142 | 142 |
| 국내 산업연관성 평가보류 | 143(이슈분석 143건 중 전부) | 143 |
| 등록 출처 | 10 | 10 |

모두 `python` 스크립트로 직접 집계한 DB 값과 화면 표시값이 일치함을 확인했다(화면이 숫자를 하드코딩하지 않음을 증명).

### 10-8. 미구현·미검증 항목(정직하게 표시)

- **실제 AI 모델 호출**: 여전히 API 키가 없어 모든 분석은 `rule_based`다. Phase 2-2·2-3과 동일한 상태이며 이번 단계에서 바뀌지 않았다.
- **비밀번호 변경 폼**: 코드는 작성·백엔드 API(`PATCH /auth/password`)는 기존에 테스트됨, 하지만 이번 단계의 브라우저 E2E에는 포함하지 않았다 — 실행 미검증.
- **수동 수집의 동시성 제어**: 같은 출처를 여러 번 빠르게 연타했을 때의 중복 실행 방지(동시 요청 잠금)는 구현하지 않았다 — 현재는 각 호출이 동기적으로 끝날 때까지 버튼이 비활성화되는 수준이다.
- **장시간 작업의 비동기 처리**: 수집·재분석 API는 여전히 동기 호출이다(백그라운드 작업 큐 없음). 지금까지의 데이터 규모(건당 수 초)에서는 문제가 없었지만, 대량 재수집 시 HTTP 타임아웃 위험이 있다.
- **이슈 병합·분리 UI**: 백엔드 API(`PATCH /issues/{id}/merge`, `POST /issues/split`)는 Phase 2-3에 이미 있으나, 이번 화면에서 버튼으로 연결하지는 못했다 — 현재는 API를 직접 호출해야 한다.
- **Docker Compose 전체 스택 실제 기동**: 여전히 미검증(로컬에 Docker 없음). CI의 서비스 컨테이너 방식으로 PostgreSQL 통합만 검증했다.

### 10-9. 다음 단계(Phase 3) 준비사항

- 보고서 집필 화면과 연결할 데이터는 이미 존재한다: 확정(`status=final`) 후보주제 → `recommended_reason`/`summary`/연결된 `issue_cluster_id`의 분석 결과(`issue_analyses`, `issue_dispute_points`, `issue_timeline_events`) → 근거 원문(`source_documents`, `document_full_texts`)까지 전부 외래키로 추적 가능하다.
- 원고 작성 화면에 필요한 신규 API: 초안 저장·버전관리(`manuscripts`/`editions` 테이블은 Phase 1부터 스키마만 존재, API 없음), 후보주제→원고 전환 엔드포인트.
- 이슈 병합·분리를 실제 화면 버튼으로 연결하는 작업.
- 실제 AI API 키 확보 시: Phase 2-2·2-3에서 이미 구현해 둔 공급자 중립 `ai_service.py` 경로를 그대로 켜고, 논쟁 탐지·국내 산업영향 분석의 실제 품질을 재검증해야 한다(현재는 전부 규칙 기반 추정치).

---

## 11. Phase 3-1 — 연구·집필 작업실 (2026-10-23)

### 11.1 구현 범위
- 후보주제 상세에서 "원고 작성 시작" → 후보·이슈 클러스터가 연결된 원고 생성(`editions`/`manuscripts`/`manuscript_versions`/`manuscript_footnotes`/`manuscript_comments`, 마이그레이션 `fcdf6b4e30c1`).
- 3분할 작업실: 목차·상태 / TipTap v3 편집기(제목·목록·표·인용·링크) / 우측 패널(원문·근거자료, 각주, 버전, 검토의견).
- 저장: 2초 디바운스 자동저장, 주요 버전(수동) 저장, 60초 간격 자동 스냅샷(내용 변경 시), 버전 비교·복원(복원도 새 주요 버전으로 기록).
- 동시 수정: `lock_version` 낙관적 잠금 → 충돌 시 409 + "최신 내용 다시 불러오기".
- 각주: 선택 영역에 원문 URL·기관·발췌·위치를 연결. 위치는 추적하지 않으면 "위치 미확인"으로 표시. **검증 상태는 기본 '미검증'이며 연구원이 명시적으로 확인할 때만 검증 완료**(자동 검증 없음). 이슈가 재검토 필요(NEEDS_REVIEW)로 바뀌면 "재검토 필요"가 실시간 계산되어 표시됨.
- 교차검토: 검토 요청 → 의견 → 수정 요청 → 해결 → 재검토 요청 → 내부 최종 승인(승인권자/관리자). 승인된 원고는 `reopen` 전까지 편집 불가. **내부 승인은 IITP 공식 선정/채택과 별개**이며 IITP 상태는 별도 필드(미제출/제출/선정/미선정).
- AI 연동 구조만 준비(원고 생성 없음). 실제 AI 호출 없음.

### 11.2 검증 결과
| 항목 | 결과 |
|---|---|
| 백엔드 pytest(SQLite) | 108개 통과(원고 11개 신규) |
| Playwright 시나리오 | A~G 7건 통과(생성·본문/표·각주·버전복원·교차검토·충돌/권한·미검증 각주) |
| `npm run build`, `npm audit` | 통과 / 취약점 0 |
| PostgreSQL | GitHub Actions CI에서 검증(아래 CI 결과 참조) |
| 시범 작성 원고 | 연방관보 FMVSS 305a NPRM(2024-04-15)·Final Rule(2024-12-20) 기반 `is_pilot` 원고 1건: 섹션 3개(추진 경과·주요 내용 및 일정·국내 시사점), 주요 버전 2건, 각주 5건(발췌문이 원문 전문과 일치한 4건만 검토자가 검증, 1건 미검증 유지), 검토 의견 1건 작성→해결. 작성자(dev-researcher-1)·검토자(dev-reviewer-1) 분리. 국내 산업 시사점은 근거가 없어 "추가 조사 필요"로 남김. 개발 DB에만 있으며 `python -m app.create_pilot_manuscript`로 재현 |

### 11.3 개발 중 발견·수정한 결함
- 각주 생성 시 디바운스 저장과 즉시 저장이 겹쳐 스스로 409 충돌 → `doSave`가 대기 타이머를 먼저 해제.
- 승인 후 편집 불가 상태에서 "저장 실패" 표시 → 비편집 상태의 `onUpdate` 무시.
- 검증 카운터가 이전 값 유지 → 각주 상태에서 파생.
- 툴바 클릭 좌표 이동으로 본문 훼손(자동화 한정) → 키보드 단축키 사용.
- PostgreSQL FK 위반(테스트의 가짜 UUID) → 실제 부모 행 생성.
- TipTap v2 취약점 → v3.32.0, Next 16.4.2로 상향.

### 11.4 한계(정직한 공개)
- 실제 AI 호출·AI 초안 생성 없음(구조만).
- 본문 안 각주 번호는 화면에 렌더링하지 않고 우측 패널의 문서 순서 번호로만 표시.
- 목차는 저장 후 갱신. 회차(edition) UI는 최소 수준.
- DOCX/PDF 내보내기, 발간본 확정은 Phase 3-2.
- 편집기 `setEditable`이 update 이벤트를 발생시켜 로드 직후 자동저장이 한 번 일어나던 결함을 CI에서 발견·수정(동시 편집 시나리오 F가 CI에서만 실패).
- 오류 경로에 `window.alert`가 일부 남아 있음.
- 페이지·문단 위치는 자동 추적하지 않아 "위치 미확인"으로 표시.

---

## 12. Phase 3-2 — 보고서·요약본 제작 및 DOCX/PDF 출력 (2026-10-23)

### 12.1 구현 범위
- **보고서 구성**(`/reports`): 일반호(주요 이슈·주요국 동향·ICT 9대 분야 단신·주요 일정 4개 파트, 앞 2개 필수), 특집호(목차 강제 없음 — 소제목·순서 직접 지정), 요약본(원고 문장을 연구원이 직접 선택·편집). 모두 실제 API·DB에 연결(`reports`/`report_items`/`report_templates`/`report_exports`, 마이그레이션 `8dd33b29ff20`).
- **DOCX 엔진**(`services/report_docx.py`, python-docx + OOXML 직접 조작): 실제 Word 각주(`word/footnotes.xml`), Word TOC 필드, 표(제목행 반복·행 분할 방지·셀 병합), 하이퍼링크, 글머리표·번호목록, 굵게·기울임·밑줄, `[표 파트-번호]` 자동 캡션, 머리글·바닥글·PAGE 필드, 표지, 맑은 고딕 설정.
- **PDF**(`services/report_pdf.py`): LibreOffice headless 변환 → PyMuPDF로 실제 페이지 수·제목별 시작 페이지·파트별 분량 계산. **목차 페이지 번호는 PDF를 실제로 렌더링해 알아낸 값만** 넣는다(2-pass). LibreOffice가 없으면 번호를 넣지 않고 안내 문구를 남기며 PDF는 '생성 불가'로 실패 기록(가짜 PDF 없음).
- **스냅샷 출력**: 누르는 순간 원고 본문·각주·템플릿 버전을 JSON으로 고정해 생성(출력 도중 원고가 바뀌어도 한 파일에 버전이 섞이지 않음). 출력본마다 파일명·SHA-256·크기·페이지/각주/표 수·사용한 원고 `lock_version`·템플릿 버전·점검 결과·성공/실패를 `report_exports`에 기록. 같은 보고서·형식의 진행 중 출력이 있으면 중복 요청 409.
- **발간 점검**(`run_preflight`): 필수 파트 누락, 빈 원고, 미검증 각주, 미승인 원고, 근거 연결 없는 수치·일정 문장(휴리스틱 경고), 요약문 재검토 필요, IITP 미확인·임시 템플릿·시범 원고 안내, **실제 렌더링 기준** 파트 분량(주요 이슈·주요국 동향 10쪽 초과 경고).
- **출력용 확정**: 승인권자/관리자만. 필수 점검(필수 파트·빈 원고·미검증 각주·미승인 원고·요약 재검토) 미통과 시 차단, 예외 사유를 남기면 확정 가능(감사 로그 기록). 확정 후 구성 변경은 409, 승인권자의 '확정 해제' 필요. **출력용 확정 ≠ IITP 공식 확인**(`iitp_confirmed` 별도).
- **템플릿**: 서식 수정 = 새 버전 행(이전 버전 보존, 관리자 전용). `임시 표준 템플릿`(IITP 공식 양식 아님, `is_provisional`). 각주 표기 규칙은 `footnote_format`으로 변경 가능. HWPX는 확장 항목으로 남김(미구현).
- **본문 각주 번호**: 편집기 본문에 `[n]` 표시(CSS 카운터, 문서 순서대로 자동), 번호 클릭 시 오른쪽 패널에서 해당 근거 강조. 각주 패널 번호 매칭 오류(`id` ↔ `mark_id`)도 수정.
- **권한**: 보고서 작성자 또는 검토자 이상만 출력 파일 목록·다운로드·구성 수정 가능(타 연구원 403, 비로그인 401). 파일은 서버 로컬 `storage/exports`(gitignore)에만 저장되고 인증된 API로만 내려받는다.

### 12.2 검증 결과
| 항목 | 결과 |
|---|---|
| 백엔드 pytest(SQLite, LibreOffice 포함 로컬) | 15개 신규(`test_reports.py`) 포함 전체 통과 |
| Playwright E2E | 기존 13 + 신규 3(시나리오 H·I·J) = 16 통과 — 실제 DOCX·PDF 다운로드 이벤트, PDF 미리보기, 출력 이력 재다운로드, 요약문 재검토 표시, 확정 차단·예외 승인 |
| 실제 파일 열람 | 생성된 DOCX를 python-docx로 재열람·zip 검사, LibreOffice로 PDF 변환·렌더링, PyMuPDF로 텍스트·페이지 추출 및 페이지 PNG 육안 점검 |
| Microsoft Word 실제 열람 | **미검증**(이 환경에 Word 없음 — LibreOffice·python-docx로만 확인) |
| PostgreSQL / CI | GitHub Actions(Ubuntu + LibreOffice + Noto CJK)에서 검증(아래 CI 결과 참조) |
| 시범 출력물 | `python -m app.create_pilot_reports` — 일반호·요약본(Phase 3-1 FMVSS 305a 시범 원고, 미완성 파트는 비움, 미검증 각주 1건 유지), 특집호·확정 흐름(`[합성 테스트 데이터]` 원고, 긴 표 34행·각주 11건) |

### 12.3 실제 렌더링 점검에서 발견·수정한 결함
- 본문 H1과 원고 제목 중복(`[시범]` 머리표 차이로 중복 판정 실패) → 정규화 비교.
- 빈 파트마다 빈 페이지 발생 → 내용 없는 파트는 새 페이지를 강제하지 않음.
- 제목 스타일이 이탤릭으로 렌더링 → 명시적으로 해제.
- 요약문에 각주 번호가 `12`처럼 붙어 보임 → 위첨자 쉼표로 구분.
- 시범 원고 각주 `anchor_text`에 내부 키가 들어가 요약문 각주 매칭 실패 → 실제 문장으로 보정.
- 파트 분량 계산이 같은 페이지를 공유하는 파트에서 0쪽 → 제목이 페이지 맨 위인지 판정해 보정.
- 편집기: 제목 입력란 수정이 저장되지 않던 문제, 저장 중 연속 입력 시 오래된 `lock_version`으로 스스로 409 충돌을 내던 문제(저장 대기열·최신 ref 사용), 편집기 `window.alert` 제거(인라인 오류 표시).
- 보고서 화면: 긴 원고 제목이 select를 넓혀 옆 칸이 버튼을 덮던 레이아웃 문제(E2E가 발견).

### 12.4 한계(정직한 공개)
- 공식 IITP 양식이 저장소에 없어 **임시 표준 템플릿**만 제공(템플릿 버전 구조는 준비됨). HWPX 출력 미구현.
- 표·그림 번호는 `[표 파트-n]` 자동이며 표 제목 텍스트 입력은 미지원(그림 번호 미구현).
- DOCX 목차는 Word TOC 필드(캐시 번호는 LibreOffice 렌더링 기준) — Word에서 열면 필드 갱신 시 번호가 달라질 수 있음. Word 실제 열람은 미검증.
- 각주 수식 규칙(`footnote_format`)은 API로만 변경 가능(관리 화면 없음). 실제 AI 호출·자동 요약 없음. 카드뉴스·주간기술동향지·메일 발송·IITP 업로드는 범위 밖.
- 근거 연결 없는 수치·일정 점검은 정규식 휴리스틱이라 오탐·누락 가능.
- 글꼴: Windows는 맑은 고딕, CI(Ubuntu)는 fontconfig 별칭으로 Noto Sans CJK KR(OFL)로 대체되어 줄바꿈이 다를 수 있음. 저장소에 글꼴 파일을 포함하지 않음.

---

## 13. Phase 3-3 — 카드뉴스 제작·편집·검증 및 PPTX/PNG 출력 (2026-10-26)

### 13.1 구현 범위
- **생성 경로 3가지**(`/card-news`): ① 기존 보고서에서(원고 문장 선택) ② 요약본에서 ③ 직접 작성. 보고서에서 만들 때 **원고에 실제로 있는 문장만** 선택할 수 있고(임의 문장 422), 선택한 문장은 `source_sentence`·원고 버전과 함께 저장된다. 원고가 바뀌면 카드에 "원본 변경·재검토 필요"가 표시되며 이미 편집한 카드 내용은 자동으로 덮어쓰지 않는다.
- **디자인 템플릿 4종**(색만 다른 것이 아니라 구성이 다름): A 핵심 요약형(핵심 내용 3박스+시사점) / B 추진 일정형(날짜별 타임라인, 발표·의견수렴 마감·확정·시행·준수 시한 구분) / C 주요국 비교형(PowerPoint 표+차이·공통점·국내 시사점) / D 핵심 수치형(핵심 수치+막대 그래프). 각 템플릿에 표지·본문·마무리 카드가 있고 카드 수·순서는 자유롭게 조정. 기본 규격 **7×15.62cm**(작업용 값, IITP 공식 규격 아님 — 건별·템플릿 버전별로 변경 가능), 색상 네이비 1B2A4A·그레이 6E7685·그린 5CAD8E·화이트+파스텔.
- **3분할 웹 편집기**: 카드 목록(썸네일·추가·복제·삭제·순서 변경) / 카드 미리보기 / 속성(내용·서식·배경색·그래프 데이터·원문 근거·검토·출력·버전). 저장은 요청을 한 줄로 직렬화해 스스로 만드는 409를 막고, 동시 수정은 `lock_version`으로 감지.
- **원문 근거·검증**: 사실·수치·일정·정책명 요소는 근거(URL·기관·발췌)를 연결해야 하며, **원고 각주가 검증되었어도 카드에서는 연구원이 따로 "검증 완료"를 눌러야** 한다. 검증 시점의 요소 텍스트 해시를 저장해 이후 수정하면 "수정됨·재검증 필요"가 된다. 그래프는 수치·단위·기준연도·비교대상·출처가 갖춰지고 근거가 검증(또는 합성 데이터로 명시)되었을 때만 그리고, 아니면 메시지 중심 레이아웃으로 전환한다.
- **PPTX**(python-pptx): 글자는 텍스트 상자, 도형·선·배경은 PowerPoint 도형, 비교표는 PowerPoint 표, 막대 그래프는 임베디드 엑셀 데이터가 있는 PowerPoint 차트(데이터 편집 가능). **슬라이드 전체를 이미지로 넣지 않으며**(테스트로 검증) 도형 이름에 요소 ID가 남는다. 슬라이드 크기가 규격과 정확히 일치.
- **PNG**: 같은 PPTX를 LibreOffice로 렌더링해 카드별 PNG 생성(HTML 화면 캡처 아님). 짧은 변 1000/1500/2000px 선택, 해상도·비율을 기록하고 ZIP·카드별 다운로드. 웹 미리보기·PPTX·사전점검은 모두 같은 장면(scene) 데이터를 사용.
- **사전점검**: 글자 잘림(글자 폭 추정+실제 렌더링 확인), 텍스트 상자 겹침, 카드 이탈, 작은 글자(<7pt), 대비 부족, 과다 글자 수, 출처 누락, 근거 없는 수치, 카드 간 제목 크기 불일치, 제목 누락, 렌더링 결과의 글자 이탈·누락.
- **검토·버전·출력 이력**: 자동 스냅샷(60초 간격)·주요 버전·복원(복원 전 상태도 보존), 카드별 검토 의견, 검토 요청→수정 요청→해결→재검토→승인권자 내부 확정(필수 점검 미통과·미해결 의견 시 예외 사유 필요), **내부 확정 ≠ IITP 공식 확인**(별도 플래그), 확정 후 수정 차단·확정 해제·새 수정 버전(복사). 출력본마다 내용 버전·템플릿 버전·SHA-256·크기·해상도·승인 상태·점검 결과 기록. 인증된 API로만 다운로드(타 연구원 403).
- DB: `card_news`, `card_news_cards`, `card_news_elements`, `card_news_templates`, `card_news_evidence`, `card_news_versions`, `card_news_reviews`, `card_news_exports`(마이그레이션 `9a8ae049aacc`).

### 13.2 검증 결과
| 항목 | 결과 |
|---|---|
| 백엔드 pytest | 카드뉴스 23건 신규(템플릿 4종 구조·보고서 연계·위조 문장 거부·근거 검증·수정 후 재검증·원본 변경 감지·카드 조작·템플릿 변경·버전 복원·검토/승인 권한·PPTX 객체 구조·표·차트 임베디드 데이터·PNG 해상도·권한) |
| Playwright E2E | 신규 3건(K 보고서 연계 생성→편집→새로고침·재로그인 유지→카드 조작→템플릿 변경→근거 검증·재검증, L PPTX·PNG 실제 다운로드·해상도·비율·이력, M 검토→수정 요청→해결→내부 확정→수정 차단→새 수정 버전) |
| 실제 렌더링 | 시범 카드뉴스 4종(A·B는 FMVSS 305a 시범 원고 기반, C·D는 합성 데이터) PPTX를 LibreOffice로 PNG(1000×2232px) 렌더링해 카드별 육안 점검 |
| Microsoft PowerPoint 실제 열람 | **미검증**(이 환경에 PowerPoint 없음 — python-pptx 재열람·LibreOffice 렌더링으로만 확인) |

### 13.3 렌더링·E2E에서 발견·수정한 결함
- 도형 그림자(스타일 effectRef)·선 그림자 → 평면 도형으로.
- 푸터 문구가 길어 줄바꿈·출처와 겹침, 작은 라벨 상자 잘림, 명도 대비 부족(배지·번호·회색 글자) → 좌표·색 조정(템플릿별 진한/연한 강조색).
- 그래프 캡션이 축 라벨과 겹침, 수치가 없을 때 메시지 중심 레이아웃에 큰 빈 공간 → 배치 조정.
- 날짜가 줄바꿈 위치에서 `2027.9.1`/`.)`로 끊김 → 쉼표 뒤 공백으로 문장 수정(근본적으로는 사전점검에서 잡을 수 있도록 한계에 기록).
- 근거 목록과 "근거 필요 여부" 플래그가 같은 필드명(`evidence`)으로 덮어쓰여 모든 요소에 근거 패널이 뜨던 버그(E2E 발견) → `evidence_required`로 분리.
- React 제어 select의 `onChange` 값을 비동기 콜백에서 읽어 템플릿 변경이 원래 값으로 전송되던 버그(E2E 발견).
- 템플릿 A→B 변경 시 옮겨진 문장의 날짜가 날짜 칸에 채워지지 않던 문제(날짜는 문장에 실제로 있을 때만 채움).

### 13.4 한계(정직한 공개)
- 실제 AI 카드뉴스 집필·AI 이미지 생성 없음. 이미지·사진 삽입 기능은 이번 단계에서 구현하지 않음(따라서 자산 사용권한 기록 구조도 미구현).
- 자유형 드래그 편집 없음 — 템플릿 기반 요소 편집과 숫자 입력(위치·크기 덮어쓰기 API만 있음)만 제공.
- 글자 폭 추정은 휴리스틱이라 PowerPoint의 실제 줄바꿈과 다를 수 있음(실제 렌더링 점검으로 보완하지만 Word/PowerPoint 자체 렌더링은 미검증). 글꼴은 Windows는 맑은 고딕, CI(Ubuntu)는 Noto CJK 대체. 나눔스퀘어 등은 템플릿 설정으로 지정 가능하나 파일은 저장소에 포함하지 않음.
- 비교형(C)·수치형(D)은 실제 자료가 없어 합성 테스트 데이터로만 시범 출력. 공식 IITP 카드뉴스 디자인이 확보되면 템플릿 버전으로 교체 필요. 3-2의 Word 실제 호환성 미검증 과제는 그대로 유지.

## 14. Phase 3-2.1 — 보고서 출력 품질 보완 (2026-10-26)

외부 검토에서 확인된 출력 오류를 고쳤다. 신규 기능이 아니라 DOCX/PDF 품질 보완이다.

| 문제 | 원인 | 조치 |
| --- | --- | --- |
| 같은 소제목이 여러 원고에서 반복될 때 목차 쪽수가 첫 원고 쪽수로 표시 | 제목 문자열로 쪽수를 찾음 | PDF에서 제목을 순서대로(위치 커서) 찾아 항목별 쪽수 목록을 만들고 목차는 항목 순번으로 번호를 넣음 |
| 목차 항목 이동 불가 | 정적 텍스트 | 모든 목차 제목에 고유 북마크(`_Toc000001…`)와 목차 내부 하이퍼링크 |
| 목차 쪽수가 재조판 후 달라질 수 있음 | 번호 삽입 후 쪽수 변동 | 최대 3회 재조판 수렴, 결과를 `toc_verified`로 기록(미수렴 시 경고) |
| 확정본에 "원고 미배치" 문구가 남음 | 확정본에도 빈 선택 파트 출력 | 확정본에서는 빈 선택 파트를 출력에서 제외하고 로마 숫자 재부여. 필수 파트가 비었는데 확정된 경우는 "출력용 확정본(예외 승인)"으로 표기 |
| 각주 URL이 글자일 뿐 | 평문 | 실제 `footnotes.xml` 하이퍼링크 관계, 같은 출처 재인용은 "앞의 각주 n번 참조"로 축약(상태 표시는 유지) |
| 표 제목이 번호뿐 | 제목 속성 없음 | 표 `caption` 속성(편집기 "표 제목" 버튼) → `[표 1-1] 제목`, 제목행 반복·제목과 첫 행 붙임 |
| 요약본이 4쪽 | 표지·목차·쪽나눔 | 요약본 전용 `layout=compact`(간결형): 표지·목차 없음, 시범 요약본 4쪽 → 1쪽 |
| 표지 제목에서 영문 약어 줄바꿈 | 공백 분할 | 영문 토큰 사이 non-breaking space, 긴 제목은 글자 크기 자동 축소 |

- 마이그레이션 `440959a9e6bb`(`reports.layout`). 간결형은 요약본만 허용(그 외 422).
- 한계: PDF/DOCX 쪽수는 글꼴 환경에 따라 달라질 수 있어 Word에서 목차 갱신을 권장한다. "(계속)" 표 이어짐 표기는 구현하지 않았고 제목행 반복으로 대체했다. Microsoft Word 실제 열람은 미검증.
- 회귀 테스트: `apps/api/tests/test_reports_321.py` (중복 소제목·목차 링크·각주 링크·표 제목·확정본 정합성·간결형·DOCX/PDF 본문 일치).

## 15. Phase 3-3.1 — 카드뉴스 품질·사실검증 보완 및 후속 규정 알림 (2026-10-26)

외부 검토(카드뉴스 PPTX 4종·PNG 6장)의 지적을 반영했다. 가장 중요한 발견은 FMVSS 305a 시행일이 후속 규정으로 바뀐 것이었다.

### 15.1 FMVSS 305a 후속 규정 — 공식 원문 확인 결과 (연방관보 API·본문 직접 조회, 2026-10-26)

| 문서 | 공고일 | 내용 |
| --- | --- | --- |
| 2024-28707 (최종 규정) | 2024.12.20. | 시행일 2025.2.18. / 준수 시한 2025.12.22.(비상대응정보 문서화), 2027.9.1.(총중량 4,536kg 이하 그 밖의 요건), 2028.9.1.(초과) / 소량생산업체·최종단계 제조업체·개조업체는 1년 추가 유예 |
| 2025-02582 (시행일 연기) | 2025.2.14. | 시행일을 **2025.3.20.**으로 연기. 준수 시한은 변경하지 않음 |
| 2026-11072 (FMVSS 214 개정) | 2026.6.3. | 305a S9.3의 214 참조 정정(형식적 개정, 시행 2026.7.6.). 날짜·준수 시한 변경 없음 — 외부 검토 지시문에는 없던 문서로, 영향 없음 알림으로 등록 |

- 시범 원고·보고서·카드뉴스(A·B형)의 `2025.2.18.` 시행일을 후속 규정으로 정정하고 2028.9.1.·추가 유예를 보완했다. 정정은 자동이 아니라 **검토자 수정 요청 → 연구원이 원고 새 버전 작성 → 카드 직접 수정 → 근거 재검증 → 확인(ack)** 순서로 수행했고(`app/create_pilot_followup.py`), 이전 원고 버전·보고서·출력본·카드뉴스 버전은 남아 있다.
- 새 각주의 검증은 발췌문이 공식 원문(연방관보 본문)에 그대로 있을 때만 검토자 처리했고(PDF 줄바꿈 하이픈 흔적은 정규화), 2027.9.1. 준수 시한 근거는 이전처럼 **미검증으로 유지**했다.

### 15.2 후속 규정 알림 (신규)

`followup_notices`·`followup_acks`(마이그레이션 `e098a93524e7`), `/followups` API·화면.
- 후속 문서를 등록하면 기존 문서 번호(또는 URL)를 인용한 **원고 각주·카드 근거·그 원고를 쓴 보고서·그 보고서에서 만든 카드뉴스**에 '후속 규정 발견·재검토 필요'가 표시된다. 내용·검증 상태는 **자동으로 바뀌지 않는다**.
- 확인 전에는 보고서·카드뉴스의 사전점검이 `followup_pending`(필수 점검)으로 막혀 내부 확정/출력용 확정에 승인권자 예외 사유가 필요하다.
- 확인(ack)은 산출물별로 `수정 반영`/`영향 없음` + 사유(3자 이상)를 남기며, 작성자·검토자 이상만 가능하다. 검증 완료와는 별개 기록이다.
- 후보 탐지(`POST /followups/detect`): 근거로 쓰인 연방관보 문서마다 공식 API에서 같은 기관의 더 새로운 Rule 후보를 찾아 보여주되 **자동 등록하지 않는다**. 영향 범위는 URL의 문서번호 일치 휴리스틱이므로 최종 판단은 연구원이 한다.

### 15.3 카드뉴스 품질 수정

| 문제 | 조치 |
| --- | --- |
| A형 빈 항목(번호 3과 빈 상자) | 출력에서는 내용이 있는 항목만 1부터 다시 번호를 매기고 상자 높이를 키워 균형 배치(편집 화면은 입력 위치 유지) |
| `[합성 테스트 데이터]`가 줄 중간에서 끊김 / `FMVSS 305a` 분리 | 앞머리 `[..]` 묶음과 영문·숫자 토큰 사이 공백을 줄바꿈 금지 공백으로 처리. 묶음이 한 줄보다 길면 적용하지 않음(글자 중간 끊김 방지) |
| 표지·마무리 번호 없음 | 모든 카드에 `nn/NN` 번호 표시(카드 수 변경 시 자동 갱신) |
| 출처가 기관명 수준 | 근거에서 `기관 문서번호`를 만들어 PPTX 출처 텍스트에 실제 하이퍼링크, 어두운 카드는 글자색 유지를 위해 텍스트 상자 전체 링크. 슬라이드 노트에 출처 전체(문서명·발표일·URL·검증 상태), PNG ZIP에 `출처목록.txt` |
| 합성 데이터가 실제와 비슷해 보임 | 모든 합성 카드에 노란 띠 "합성 테스트 데이터 · 실제 정책·통계 아님". **합성 데이터가 포함된 카드뉴스는 내부 확정 불가**(예외 사유로도 불가) |
| 장식 원이 카드 밖으로 걸침 | 장식 도형(`deco`)은 이탈 점검에서 제외, 일반 도형의 이탈은 오류로 점검 |
| PNG 해상도 차이 | 생성 원본은 1000×2232px(출력 기록에 저장). 외부 첨부본의 917×2048은 업로드 과정의 축소로 보이며, 출처 목록에 실제 원본 크기를 기록한다 |

한계: Microsoft PowerPoint 실제 열람은 여전히 미검증(LibreOffice 렌더링·python-pptx 재열람만). PowerPoint는 하이퍼링크 글자에 테마 링크색(파랑)을 적용하므로 밝은 배경 카드에서만 글자 단위 링크를 쓴다. 한글 조사가 날짜 뒤에서 줄바꿈될 수 있다(예: `2025.3.20.` / `으로`) — 줄바꿈 금지 규칙은 영문·숫자 토큰에만 적용했다.

## 16. Phase 3-4 — 주간기술동향지 전문가 원고 의뢰·접수·심의·교정·발간본 (2026-10-26)

외부 전문가 기고문을 받아 심의·편집하는 업무 시스템이다. 주간 AI·ICT 동향보고서(연구원 직접 집필)와 별도 흐름이며 DOCX/PDF 엔진만 재사용한다.
실제 전문가 연락·이메일 발송·IITP 업로드는 하지 않는다(발송 대기 상태와 이력 구조만 있음). 모든 시범 데이터는 합성이다.

### 16.1 구성 (마이그레이션 `e0863abd4939`, 테이블 15개 `tj_*`)

| 영역 | 내용 |
| --- | --- |
| 회차·일정 | 연도별 회차 계획(25회 등록, **발간일 자동 확정 없음**) → 관리자가 발간일 입력 → D-60~50·25·22·20·15·10·7·3·0 단계 마감일 계산. D-n은 달력일/영업일, 휴일 조정(앞당김/미룸/없음)·휴일 목록을 관리자가 설정. 마감일과 실제 완료일 분리, 기한 초과는 **'지연' 표시(자동 완료 안 함)** + 후속 단계 영향 문구 |
| 집필진 DB | 전문가(식별번호·소속·복수 전문 분야·연구 소개·연락처), 중복 등록 방지(성명+소속/이메일), 개인정보 동의 상태, 비식별화(관리자), 조회 이력(감사로그), 후보 검색(집필 가능 여부는 추정하지 않음) |
| 원고 의뢰 | 의뢰서(주제·취지·목차·분량·양식·기한·연락처), 후보주제 연결(AI 추천 ≠ IITP 확정), 안내 메일 **미리보기·임시저장·발송 대기만**(발송 상태 없음), 수락·거절·미응답 이력 |
| 외부 저자 포털 | 자신의 의뢰·원고만 조회(타인 원고는 404), 의뢰 수락/거절, DOCX·PDF 제출, 형식 보완 재제출, 제출서류 첨부, 검토 의견 확인(검토자 이름 숨김)·답변, 수정본 재제출 |
| 접수·보안 | 확장자·시그니처 일치, **매크로(VBA)·ActiveX·임베디드 OLE·외부 템플릿·PDF 스크립트/자동 실행/첨부 파일·압축 폭탄 거부**, 용량 제한, 버전별 SHA-256·크기·업로더 기록, 파일 덮어쓰기 없음, 파일은 서버 로컬 저장소에만 두고 인증된 API로만 내려받음 |
| 형식 점검 | 제목·영문 제목·저자·소속·요약·참고문헌·표·그림 번호·제목 점검. **분량·제출서류·표절률은 관리자가 설정한 기준만 적용**(미설정이면 '기준 미설정' 표시, 과거 모집안내 수치를 넣지 않음). 형식 검토와 내용 검토는 별도 상태 |
| 검토·심의 | 검토자 배정(1·2차, 내부/외부 검토자, 기한), **이해상충 경고(같은 소속 자동 감지·신고, 검토자 본인 확인 필수)**, 문서·문단·표·그림 단위 의견, 저자 답변·해결 구분(답변≠해결), 검토자 추천 의견은 참고용, **심의 결과 확정은 승인권자·관리자만**(결과 구분은 관리자가 변경), 미해결 수정 요청이 있으면 게재 확정 차단 |
| 버전 비교 | 문단 추가·삭제·수정 비교, 표·그림·각주·변경내용 추적이 있으면 **'원본 파일 비교 필요'** 표시, 검토 의견↔수정 대응(수정 확정으로 단정하지 않음), 수정 폭이 크면(기본 30%) 이전 검토 유효성 재검토 표시 |
| 교정·발간본 | 교정본 새 버전 업로드, 점검표(원문 출처·그림/표 번호·참고문헌·약어·문장 오류) 전부 확인해야 최종 교정 확인, 게재 순서 지정, **임시 주간기술동향지 템플릿**(버전 관리, 보고서 양식과 분리), 표지·목차·원고별 시작 페이지·제목·저자·소속, 출력 시점의 원고 버전·해시 고정, 확정 발간본은 승인권자·관리자만(필수 점검 통과 필요), 발간 이력 기록은 내부 이력이며 IITP 확인과 별개 |
| 대시보드 | 연간 계획·발간일 입력·의뢰 상태·원고 상태·검토 현황·지연/임박 업무, 담당 회차만 보기, 실적은 **DB 집계(계획 건수와 발간 기록 건수 분리, 25 하드코딩 없음)** |

### 16.2 권한

외부 집필(`author`)·외부 검토(`ext_reviewer`) 역할을 추가했고, 앱 전역 의존성(`guard_external_users`)이 이 계정의 포털(`/journal/portal`)·인증 외 모든 내부 API 접근을 서버에서 차단한다. 내부 검토자(`reviewer`)도 편집 API는 쓸 수 없고 자신에게 배정된 원고만 포털에서 본다.
편집(researcher·approver·admin) / 게재 확정·확정 발간본·IITP 확인 기록(approver·admin) / 설정·발간일·계정 생성·비식별화(admin).

### 16.3 한계·미구현 (정직한 보고)

- **Microsoft Word 실제 호환 미검증**(LibreOffice·python 라이브러리로만 확인). 공식 IITP 주간기술동향지 양식이 없어 임시 템플릿이다.
- 저자 DOCX의 **그림·각주·셀 병합·수식·변경내용 추적은 발간본에 자동 변환되지 않는다**(감지해 경고하고 원본은 보존). 표와 문단·제목·목록·굵게/기울임/밑줄만 변환한다. PDF 원고는 본문 변환 불가(DOCX 교정본 필요).
- 외부 표절검사 서비스 미연동(결과 파일 업로드·담당자 확인 기록만). 안티바이러스 연동 없음(1차 정적 검사).
- 이메일·알림 발송 없음(대시보드 표시만), 개인정보 보존 기간 만료 자동 삭제 스케줄러 없음(수동 비식별화).
- 기한 알림은 대시보드 표시이며 푸시·메일은 Phase 3-5 이후.

### 16.4 Phase 3-3.2 (카드뉴스 잔여 보완, 3-4 지시문 §14)

C형 마무리 카드의 장식 띠가 카드 번호를 가리던 문제 수정, 타임라인에 '시행일 변경' 구분 추가, 마무리 카드 라벨의 '향후 일정'을 '주요 시행·준수 일정'으로(지난 날짜가 섞여도 오해 없게), 카드 출력물에 **'근거 미검증' 배지**(검증되지 않은 근거·근거 없는 핵심 내용이 있는 카드, 합성 카드는 노란 띠로 대체), 짧은 괄호 표기 `(합성)`이 줄 첫머리에 홀로 놓이지 않게 처리.

## 17. Phase 3-5 — 시연 통합·원문 링크·요약본 사실 재검토·심의 확정 통제·공개 `/preview/` (2026-10-26)

**목적**: 이미 만든 기능이 실제 브라우저에서 끝까지 이어지는지 확인하고, 시연에서 막히는 부분(무반응 버튼·가짜 건수·원문 링크 없음)을 제거한다.

1. **원문 링크**: 뉴스 제목 클릭은 공식 원문을 새 탭(`rel="noopener noreferrer"`)으로 연다. `services/link_quality.py`가 주소를 `missing/invalid/homepage/search/document`로 분류한다. 주소가 없거나 올바르지 않으면 클릭을 막고 사유를 보이며, 기관 홈페이지·검색 화면으로 보이면 열 수는 있되 '주소 확인 필요'를 표시한다. '링크 접속 점검'은 404/410(삭제)과 401/403/429(접속 제한)·시간초과(확인 불가)를 구분하며 접속 실패만으로 주소를 틀렸다고 단정하지 않는다.
2. **목록·필터**: 분야는 분류 결과 기준이며 자료 없는 분야는 빈 상태. 검색은 제목과 확보한 원문을 함께 본다. 조건은 URL에 남아 뒤로가기 후 유지, 결과 건수는 실제 조회 수(`total`).
3. **이슈·후보주제**: 이슈 병합(확인 필요)·분리(복구 가능), 후보주제 담당자·설명 수정·수정 이력(감사 로그의 변경 전후), 근거 원문의 외부 링크.
4. **요약본 핵심 사실 재검토(P0-1)**: 원고가 바뀌면 요약본 문장과 원고 문장의 날짜·수치를 비교(`fact_diff`)하여 사라진/새로 생긴 사실을 보여준다. 요약본에 과거 시행일이 남아 있으면 자동으로 고치지 않고 '재검토 필요'를 유지하며, 검토자가 '수정 반영'(요약 문장 수정 필요)/'영향 없음' 중 하나와 사유(3자 이상)를 기록해야 해소된다. 이력은 `fact_reviewed_by/at/lock_version`과 감사 로그로 남는다. **원고가 다시 바뀌면 `fact_reviewed_lock_version` 불일치로 재검토가 다시 요구된다**.
5. **심의의견 확정 통제(P0-2)**: 저자 답변과 검토자 해결은 별개 상태다. 미해결 필수의견이 남은 채 확정(수락)하려면 approver/admin이 예외 사유를 입력해야 하며 `exception_reason`·`unresolved_count`가 결정 기록에 남고 대시보드에 표시된다. 표·그림에 대한 의견은 'unchanged'로 추정하지 않고 '원본 확인 필요'로 표시한다.
6. **P1**: 기술동향지 표 캡션이 본문 캡션 문단과 중복되던 것을 병합, DOCX/PDF 제목은 단어 경계에서 줄바꿈(`_wrap_by_words`).
7. **공개 `/preview/`**: `python -m app.export_public_snapshot`이 허용 목록 방식으로 JSON을 만든다(문서 메타데이터·이슈·근거 이슈가 있는 후보주제만). 후보주제 `summary`(원문 발췌에 저자명·이메일 가능)·검토의견·사용자·원문 전문·시범/E2E 자료는 제외하고, 이메일을 제거한 뒤 남아 있으면 `PrivacyError`로 중단한다. 화면은 읽기 전용이며 '정적 스냅샷·기준일'을 상시 표시하고 저장·로그인·파일 생성은 지원하지 않는다고 밝힌다. 기존 `index.html`은 그대로다.

**검증**: pytest 225건, Playwright 26건(신규 `phase3-5-demo.spec.ts`: 분야→목록→원문 새 탭, 링크 없음 차단, 필터·뒤로가기 유지, 빈 분야, 후보 수정 유지), tsc 통과. 요약본 재검토(K)·필수의견 확정 차단(L)은 `test_phase35.py`와 기존 주간기술동향지 E2E(P·Q)가 다룬다.
**미검증/한계**: Word·PowerPoint 실열람, 외부 사이트 실제 접속(검증 환경 의존), IITP 공식 양식 대조.
