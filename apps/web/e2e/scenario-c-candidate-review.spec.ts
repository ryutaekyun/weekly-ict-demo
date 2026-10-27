import { test, expect } from "./fixtures";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 C — 추천 후보 확인 → 평가 근거 검토 → 의견 작성 → 저장 → 새로고침 → 재확인", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/candidates");
  await expect(page.getByRole("heading", { name: "후보주제 선정·검토" })).toBeVisible();
  await page.locator("table tbody tr td a").first().click();

  // 평가 근거(가중점수 또는 '평가 보류')가 화면에 보여야 한다
  await expect(page.getByText(/부분 평가점수|점$/).first()).toBeVisible({ timeout: 10_000 });

  const comment = `Playwright E2E ${Date.now()}`;
  await page.getByPlaceholder("검토 의견을 입력하세요").fill(comment);
  await page.getByRole("button", { name: "등록" }).click();
  await expect(page.getByText(comment)).toBeVisible();

  await page.reload();
  await expect(page.getByText(comment)).toBeVisible();
});
