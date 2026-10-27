import { test, expect } from "@playwright/test";
import { login, logout, E2E_ADMIN, E2E_RESEARCHER } from "./helpers";

test("시나리오 F — 일반 연구원은 관리자 전용 기능이 차단되고, 허용된 기능(검토의견)은 실행된다", async ({ page }) => {
  await login(page, E2E_RESEARCHER);

  await page.goto("/documents?relevance=matched"); // 분류가 끝난 자료만 대상으로 한다(미처리 자료에 분류 저장을 눌러 데이터를 오염시키지 않도록)
  await page.getByRole("link", { name: /^상세 분석/ }).first().click(); // 제목은 외부 원문(새 탭), 상세 분석은 플랫폼 내부 화면

  // FastAPI가 서버 측에서 require_roles(admin, approver, reviewer)로 막아야 한다 — 프런트 숨김이 아니라 실제 403.
  await page.locator("form", { hasText: "분야 분류" }).getByRole("button", { name: "분류 저장" }).click();
  await expect(page.getByText(/권한이 필요합니다/)).toBeVisible();

  // 연구원도 할 수 있는 일(후보 검토의견 작성)은 정상 동작해야 한다
  await page.goto("/candidates");
  await page.locator("table tbody tr td a").first().click();
  const comment = `연구원 권한 테스트 ${Date.now()}`;
  await page.getByPlaceholder("검토 의견을 입력하세요").fill(comment);
  await page.getByRole("button", { name: "등록" }).click();
  await expect(page.getByText(comment)).toBeVisible();

  await logout(page);

  // 관리자 계정에서는 분류 수정이 허용되어야 한다
  await login(page, E2E_ADMIN);
  await page.goto("/documents?relevance=matched"); // 분류가 끝난 자료만 대상으로 한다(미처리 자료에 분류 저장을 눌러 데이터를 오염시키지 않도록)
  await page.getByRole("link", { name: /^상세 분석/ }).first().click(); // 제목은 외부 원문(새 탭), 상세 분석은 플랫폼 내부 화면
  await page.locator("form", { hasText: "분야 분류" }).getByRole("button", { name: "분류 저장" }).click();
  await expect(page.getByText("분류가 저장되었습니다")).toBeVisible();
});
