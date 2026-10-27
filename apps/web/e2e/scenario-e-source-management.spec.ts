import { test, expect } from "./fixtures";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 E — 관리자 로그인 → 출처 선택 → 지금 수집(작업 상태 조회) → 수집 결과 확인", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "출처·수집 관리" })).toBeVisible();
  await expect(page.getByText(/총 \d+곳/)).toBeVisible();

  // 실제 수집 엔진이 서버에서 작업으로 실행된다(외부 네트워크) — 작업 상태가 끝날 때까지 상태 값을 조건으로 기다린다.
  await page.getByTestId("collect-now").first().click();
  const status = page.getByTestId("job-status").first();
  await expect(status).toHaveAttribute("data-job-status", /^(succeeded|failed|timeout|cancelled|interrupted)$/, { timeout: 240_000 });
  await expect(status).toContainText(/신규 \d+건 · 중복 \d+건 · 수정 \d+건/);
});
