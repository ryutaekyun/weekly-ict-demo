import { test, expect } from "@playwright/test";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 D — 문서 선택 → 분류 수정 → 저장 → 새로고침 후 반영 확인", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/documents");
  await page.locator("table tbody tr td a").first().click();

  const ratingSelect = page.locator("form", { hasText: "실무 활용성 평가" }).locator("select");
  const current = await ratingSelect.inputValue();
  const next = current === "priority" ? "needs_more_info" : "priority";

  await ratingSelect.selectOption(next);
  await page.locator("form", { hasText: "실무 활용성 평가" }).getByRole("button", { name: "평가 저장" }).click();
  await expect(page.getByText("실무 활용성 평가가 저장되었습니다")).toBeVisible();

  await page.reload();
  await expect(page.getByText("연구원 수정됨")).toBeVisible();
  await expect(page.locator("form", { hasText: "실무 활용성 평가" }).locator("select")).toHaveValue(next);
});
