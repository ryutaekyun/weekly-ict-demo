# 배포 가이드 — TNP 실제 업무용 서비스 (Phase 4-1)

기준일 2026-10-27. **현재 상태: 로컬 개발 PC에서 화면·가입·승인·공동 DB 사용은 검증 완료. 회사 서버/외부 접속 배포는 미완료**(아래 '미검증' 참고). 작동하지 않는 구성을 배포 완료로 표시하지 않는다.

## 1. 구조
| 구성요소 | 기술 | 비고 |
|---|---|---|
| 화면 | Next.js | 같은 도메인의 `/api` 경로로 API 호출 |
| 서버 | FastAPI(uvicorn) | 시작 시 `alembic upgrade head`, `APP_ENV=production`이면 약한 JWT 비밀키·Secure 쿠키 꺼짐을 거부하고 `/docs` 비공개 |
| DB | PostgreSQL 16 | 외부 포트 비공개, 볼륨 `tnp_db_data`에 영속 저장 |
| 파일 | 볼륨 `tnp_files` | 생성한 DOCX/PDF·주간기술동향지 첨부 |
| HTTPS | Caddy | 공인 도메인이면 Let's Encrypt 무료 자동 발급, 사내 이름이면 내부 인증서 |
| 수집 작업자 | Python(`python -m app.worker`) | Phase 4-2 구현 — 로컬 검증, 서버(Docker) 상시 구동은 미검증. 번역 작업자는 4-3 |

구성 파일: `infra/docker-compose.prod.yml`, `infra/Caddyfile`, `infra/.env.prod.example`, `infra/backup.sh`, `infra/restore.sh`.

## 2. 비용·라이선스 검토
- Next.js·FastAPI·PostgreSQL·Caddy·Docker Engine은 상업적 이용이 가능한 무료 오픈소스다. **Docker Desktop**(Windows)은 직원 250명 미만·연매출 1천만 달러 미만 기업은 무료이나 TNP의 해당 여부는 TNP가 확인해야 한다(확인 전에는 설치하지 않았다).
- **Vercel Hobby**는 비상업적 개인 용도 한정이라 회사 업무용에 맞지 않고, FastAPI·PostgreSQL 상시 구동에도 적합하지 않다. 유료 요금제는 신청하지 않았다.
- 무료 외부 클라우드(예: 무료 티어)는 휴면·용량·상업 이용 제한이 있어 업무 서비스의 기본 선택으로 권하지 않는다.

## 3. 권장 방식 — 회사 보유 PC/서버 1대(상시 켜 둠)
1. 서버에 Docker(+Compose)를 설치한다(Linux 서버면 Docker Engine이 무료, Windows면 위 라이선스 확인 후 Docker Desktop 또는 WSL2).
2. `infra/.env.prod.example`을 `infra/.env.prod`로 복사해 `PUBLIC_HOST`, `POSTGRES_PASSWORD`, `JWT_SECRET`을 채운다(저장소에 올리지 않는다).
3. `docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod up -d --build`
4. 첫 관리자 계정: 컨테이너에서 `python -m app.seed` 또는 `seed_demo_accounts`로 가상 계정이 아닌 **실제 관리자**를 만든 뒤(초기 비밀번호는 출력되는 값을 즉시 변경), 이후 연구원은 `/register`로 가입하고 관리자가 `/admin/users`에서 승인하거나 초대 링크를 발급한다.
5. 접속: 사내망은 `https://<서버 이름>`, 외부 접속은 공유기/방화벽 80·443 포트 개방 + 도메인 DNS 연결이 필요하다(회사 IT 승인 사항).

## 4. 백업·복원
- 백업: `sh infra/backup.sh` → `backups/<일시>/db.dump` + `files/`. 복원: `sh infra/restore.sh <폴더> --yes`(복원 직전 현재 상태를 자동 백업). 개발 SQLite는 `python -m app.demo_data backup|restore`.
- 정기 백업은 서버 작업 스케줄러(cron/작업 스케줄러)로 매일 실행하고 사본을 다른 저장소에 둔다.
- **복원 시험은 Docker 환경에서 아직 실행하지 못했다(미검증).**

## 5. 데이터 분리
- 개발 DB(`apps/api/dev.db`)에는 자동 테스트가 만든 가상 데이터(E2E)가 섞여 있다. **실제 업무 DB는 새 PostgreSQL에서 시작**하고, 실제 수집 데이터는 Phase 4-2의 수집기로 다시 확보한다. 필요하면 개발 DB의 실제 수집 자료(테스트 표지 제외)만 내보내 이전한다(미구현).

## 6. 보안 체크리스트
- 비밀번호 해시 저장(기존), 승인 전 접근 차단(서버 검증), 로그인 5회 실패 잠금, CSRF·httpOnly 쿠키, 운영에서 `/docs` 비공개, 초대 토큰은 해시만 저장.
- 인증정보(.env, 백업, DB)는 저장소에 올리지 않는다(`.gitignore`). 과거 커밋 노출 점검 결과는 최종 보고에 기재한다.

- 저장소 이력 점검(2026-10-27): 모든 브랜치 커밋에서 API 키·개인키·토큰 형태를 검색한 결과 **실제 키는 없었고**, 테스트용 가짜 문자열(`sk-ant-fake-…`)만 있었다. 따라서 폐기·교체가 필요한 노출 인증정보는 발견되지 않았다. 자동 테스트용 고정 비밀번호(`e2e-*@example.com`)는 저장소에 있으나 테스트 DB 전용이며, 운영(`APP_ENV=production`)에서는 해당 계정 생성 스크립트가 실행되지 않도록 막았다.

## 6-1. 수집 작업자 운영
- 개발 PC(Windows): `scripts\start-worker.ps1`(상시) 또는 작업 스케줄러에서 `apps\api\.venv\Scripts\python -m app.worker --once` 를 15~60분마다 실행. 로그: `apps/api/storage/logs/worker.log`.
- Docker: `docker-compose.prod.yml`의 `worker` 서비스가 같은 이미지로 `python -m app.worker` 를 실행한다(미검증).
- 서버 설정: `COLLECTOR_ALLOW_PRIVATE_HOSTS` 는 자동 테스트 전용이며 `APP_ENV=production` 에서는 켜면 서버가 시작되지 않는다.

## 7. 미검증·미구현
- Docker/PostgreSQL 실서버 기동, HTTPS 인증서 발급, 외부 PC 접속, 서버 재시작 후 데이터 유지, 백업·복원 시험 — **이 PC에 Docker·WSL이 없어 실행하지 못했다.** 사용자가 서버(또는 PC)와 Docker 설치를 승인하면 같은 구성으로 검증한다.
- 현재 확인한 것: 프로덕션 빌드(`npm run build`) 성공, 회원가입·승인·초대·공동 DB를 로컬(SQLite)에서 2개 브라우저 세션으로 E2E 통과, PostgreSQL에서의 pytest는 GitHub Actions에서 확인.
