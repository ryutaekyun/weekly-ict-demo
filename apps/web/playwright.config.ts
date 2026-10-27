import { defineConfig, devices } from "@playwright/test";

// 로컬 실행은 개발 DB(dev.db)와 분리된 E2E 전용 서버를 띄운다: API 8010(DB: apps/api/e2e.db — 실행마다 dev.db 복사본으로 새로 만듦) + 화면 3100.
// CI(E2E_ISOLATED=0)는 이미 깨끗한 DB로 8000/3000 서버를 띄워 두므로 그 서버를 그대로 쓴다.
const ISOLATED = process.env.E2E_ISOLATED !== "0";
const API = process.env.E2E_API_URL ?? (ISOLATED ? "http://localhost:8010" : "http://localhost:8000");
const WEB = process.env.E2E_WEB_URL ?? (ISOLATED ? "http://localhost:3100" : "http://localhost:3000");
const py = process.platform === "win32" ? "..\\api\\.venv\\Scripts\\python.exe" : "python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // 개발 서버(첫 컴파일·부하)에서도 화면 로딩이 5초를 넘을 수 있어 기본 단언 대기를 늘린다 — 고정 sleep 이 아니라 상태가 나타나는 즉시 통과한다
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: WEB,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    ...(ISOLATED
      ? [
          { command: `${py} ../../scripts/run_e2e_api.py`, url: `${API}/health`, reuseExistingServer: false, timeout: 120_000 },
          {
            command: "npm run dev -- -p 3100",
            url: `${WEB}/login`,
            reuseExistingServer: false,
            timeout: 120_000,
            env: { NEXT_PUBLIC_API_URL: API, NEXT_DIST_DIR: ".next-e2e" },
          },
        ]
      : [{ command: "npm run dev", url: WEB, reuseExistingServer: true, timeout: 60_000 }]),
    // 수집 E2E 전용 로컬 피드 서버 — 테스트가 feeds/*.xml 을 쓰고 고쳐 '신규→수정' 시나리오를 만든다(실제 외부 사이트가 아님을 화면·보고서에 구분 표기)
    { command: "python -m http.server 4174 --directory e2e/feeds", url: "http://localhost:4174/", reuseExistingServer: true, timeout: 30_000 },
    // 공개 /preview/ 정적 시연(GitHub Pages와 같은 파일)을 로컬에서 서빙해 같은 화면을 브라우저로 검증한다
    { command: "python -m http.server 4173 --directory ../../preview", url: "http://localhost:4173/index.html", reuseExistingServer: true, timeout: 30_000 },
  ],
});
