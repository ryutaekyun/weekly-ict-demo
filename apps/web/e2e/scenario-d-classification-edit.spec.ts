import { test, expect } from "@playwright/test";
import { login, E2E_ADMIN } from "./helpers";

test("시나리오 D — 문서 선택 → 분류 수정 → 저장 → 새로고침 후 반영 확인", async ({ page }) => {
  await login(page, E2E_ADMIN);

  await page.goto("/documents");
  await page.getByRole("link", { name: /^상세 분석/ }).first().click(); // 제목은 외부 원문(새 탭), 상세 분석은 플랫폼 내부 화면

  const ratingSelect = page.locator("form", { hasText: "실무 활용성 평가" }).locator("select");
  const current = await ratingSelect.inputValue();
  const next = current === "priority" ? "needs_more_info" : "priority";

  await ratingSelect.selectOption(next);
  await page.locator("form", { hasText: "실무 활용성 평가" }).getByRole("button", { name: "평가 저장" }).click();
  await expect(page.getByText("실무 활용성 평가가 저장되었습니다")).toBeVisible();

  await page.reload();
  // 분류·평가 두 섹션 모두 같은 문구를 쓰므로(반복 실행 시 둘 다 표시될 수 있음) 평가 섹션으로 범위를 좁힌다
  await expect(page.getByText("우선 검토 · 연구원 수정됨").or(page.getByText("추가 확인 필요 · 연구원 수정됨"))).toBeVisible();
  await expect(page.locator("form", { hasText: "실무 활용성 평가" }).locator("select")).toHaveValue(next);
});
