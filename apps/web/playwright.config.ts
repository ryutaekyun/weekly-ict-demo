import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: "npm run dev", url: "http://localhost:3000", reuseExistingServer: true, timeout: 60_000 },
    // 공개 /preview/ 정적 시연(GitHub Pages와 같은 파일)을 로컬에서 서빙해 같은 화면을 브라우저로 검증한다
    { command: "python -m http.server 4173 --directory ../../preview", url: "http://localhost:4173/index.html", reuseExistingServer: true, timeout: 30_000 },
  ],
});
