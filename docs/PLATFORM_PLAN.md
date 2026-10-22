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
