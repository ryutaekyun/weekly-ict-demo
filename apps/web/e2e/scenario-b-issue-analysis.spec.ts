import { test, expect } from "@playwright/test";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 B — 핵심 이슈 목록 → 복수 문서 이슈 선택 → 타임라인·쟁점 확인 → 연결된 원문 열기", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/issues");
  await expect(page.getByRole("heading", { name: "핵심 이슈 분석" })).toBeVisible();
  await page.getByLabel("복수 문서 이슈만").check();

  const rows = page.locator("table tbody tr");
  const rowCount = await rows.count();
  test.skip(rowCount === 0 || (await rows.first().locator("td").count()) < 2, "이 데이터셋에는 복수 문서 이슈가 없습니다");

  await rows.first().locator("a").click();
  await expect(page.getByText(/관련 문서 \d+건/)).toBeVisible();
  await expect(page.getByText("② 타임라인")).toBeVisible();
  await expect(page.getByText("관련 원문 전체 목록")).toBeVisible();

  const docLink = page.getByRole("link", { name: /^상세 분석/ }).first();
  await expect(docLink).toBeVisible();
  await docLink.click();
  await expect(page).toHaveURL(/\/documents\//);
});
