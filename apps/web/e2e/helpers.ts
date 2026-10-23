import { Page } from "@playwright/test";

// CI/로컬 Playwright 테스트 전용 고정 비밀번호 계정 — apps/api/app/seed_e2e_test_user.py 참고.
// 운영 계정이 아니며, 전부 example.com(IANA 예약 도메인)의 가상 인물이다.
export const E2E_ADMIN = { email: "e2e-admin@example.com", password: "E2eTest-Fixed-Pw-Admin-001!" };
export const E2E_RESEARCHER = { email: "e2e-researcher@example.com", password: "E2eTest-Fixed-Pw-Researcher-002!" };

export const E2E_REVIEWER = { email: "e2e-reviewer@example.com", password: "E2eTest-Fixed-Pw-Reviewer-003!" };

export async function login(page: Page, account: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByRole("textbox").first().fill(account.email);
  await page.locator('input[type="password"]').fill(account.password);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL("**/dashboard");
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.waitForURL("**/login");
}
