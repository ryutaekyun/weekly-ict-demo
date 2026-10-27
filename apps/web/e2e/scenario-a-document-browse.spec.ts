import { test, expect } from "./fixtures";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 A — 로그인 → ICT 정보 수집 → 분야 선택 → 문서 조회 → 관련 이슈 이동", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/documents");
  await expect(page.getByRole("heading", { name: "ICT 정보 수집" })).toBeVisible();

  // 인공지능·데이터 분야 선택
  await page.locator("select").first().selectOption("ai");
  // 필터 적용 후 재조회가 끝나 첫 행이 해당 분야가 될 때까지 기다린다(이전 목록의 첫 행을 읽는 경쟁 상태 방지)
  await expect(page.locator("table tbody tr").first()).toContainText("인공지능·데이터");

  // 첫 번째 문서 상세로 이동
  const title = await page.getByTestId("news-link").first().locator("a").textContent();
  await page.getByRole("link", { name: /^상세 분석/ }).first().click(); // 제목 클릭은 외부 원문, 상세 분석은 내부 화면

  await expect(page.locator("h1")).toHaveText(title ?? "");
  await expect(page.getByText("원문 전문")).toBeVisible();
  await expect(page.getByText("구조화된 핵심 내용")).toBeVisible();
});
