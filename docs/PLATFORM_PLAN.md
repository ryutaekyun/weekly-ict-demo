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
