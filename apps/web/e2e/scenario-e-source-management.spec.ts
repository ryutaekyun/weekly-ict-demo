import { test, expect } from "@playwright/test";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 E — 관리자 로그인 → 출처 선택 → 수동 수집 실행 → 수집 상태 확인", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "출처·수집 관리" })).toBeVisible();
  await expect(page.getByText(/총 \d+곳/)).toBeVisible();

  // 실제 수집 엔진을 호출하므로(외부 네트워크) 넉넉한 타임아웃을 둔다.
  await page.getByRole("button", { name: "수동 수집 실행" }).first().click();
  await expect(page.getByText(/수집 완료: 신규 \d+건 · 중복 \d+건 · 개정 \d+건/)).toBeVisible({ timeout: 30_000 });
});
