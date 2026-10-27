import { type Page } from "@playwright/test";
import { test, expect, newCtx } from "./fixtures";
import { login, logout, E2E_ADMIN, E2E_RESEARCHER, E2E_REVIEWER } from "./helpers";

async function startManuscript(page: Page): Promise<string> {
  await page.goto("/candidates");
  await page.locator("table tbody tr td a").first().click();
  await page.getByRole("button", { name: "원고 작성 시작" }).click();
  await page.waitForURL(/\/manuscripts\/[0-9a-f-]+$/);
  return page.url();
}

async function typeInEditor(page: Page, text: string) {
  await page.locator(".ProseMirror").click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type(text);
}

async function waitSaved(page: Page) {
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
}

test("시나리오 A — 후보주제에서 원고 생성(후보·이슈 컨텍스트 연결)", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await startManuscript(page);
  await expect(page.getByText("초안", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "원문·근거자료" })).toBeVisible();
  await expect(page.getByText("관련 원문")).toBeVisible();
});

test("시나리오 B — 본문 작성·표 삽입 후 새로고침해도 내용 유지", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const url = await startManuscript(page);
  const marker = `E2E본문${Date.now()}`;
  await typeInEditor(page, marker);
  await page.getByRole("button", { name: "표 삽입" }).click();
  await waitSaved(page);
  await page.goto(url);
  await expect(page.locator(".ProseMirror")).toContainText(marker);
  await expect(page.locator(".ProseMirror table")).toBeVisible();
});

test("시나리오 C — 문장에 원문 근거 연결(각주) 후 저장·재조회, 위치 미확인 표시", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const url = await startManuscript(page);
  await typeInEditor(page, "근거를 연결할 핵심 문장입니다.");
  await waitSaved(page);
  await page.locator(".ProseMirror p").first().click({ clickCount: 3 });
  await page.getByRole("button", { name: "선택 영역에 근거 연결" }).click();
  await page.getByPlaceholder("원문 URL(필수)").fill("https://example.org/official-doc");
  await page.getByPlaceholder("발표 기관").fill("예시 기관");
  await page.getByPlaceholder("근거 원문 발췌").fill("원문 발췌 내용");
  await page.getByRole("button", { name: "각주 생성" }).click();
  await waitSaved(page);
  await page.goto(url);
  await page.getByRole("button", { name: /^각주\(/ }).click();
  await expect(page.getByText("https://example.org/official-doc")).toBeVisible();
  await expect(page.getByText("위치 미확인")).toBeVisible();
  await expect(page.locator(".ProseMirror .footnote-ref")).toBeVisible();
  // 본문에 각주 번호([1])가 표시되고, 누르면 오른쪽 패널의 해당 근거 카드가 강조된다(Phase 3-2)
  const shown = await page.locator(".ProseMirror .footnote-ref").first().evaluate((el) => getComputedStyle(el, "::after").content);
  expect(shown).toContain("counter(fnnum)"); // 번호는 CSS 카운터로 문서 순서대로 매겨진다(계산값은 스크린샷으로 확인)
  await page.locator(".ProseMirror").screenshot({ path: "test-results/footnote-number.png" });
  await page.getByRole("button", { name: /^버전\(/ }).click();
  await page.locator(".ProseMirror .footnote-ref").first().click();
  await expect(page.getByText("https://example.org/official-doc")).toBeVisible();
});

test("시나리오 D — 주요 버전 저장 후 수정, 이전 버전 복원", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await startManuscript(page);
  await typeInEditor(page, "버전1 본문");
  await page.getByRole("button", { name: "주요 버전 저장" }).click();
  await page.getByPlaceholder("예: 1차 초안 완료").fill("1차 초안");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await waitSaved(page);
  await typeInEditor(page, " 추가수정내용");
  await page.getByRole("button", { name: "주요 버전 저장" }).click();
  await page.getByPlaceholder("예: 1차 초안 완료").fill("2차 수정");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await waitSaved(page);

  await page.getByRole("button", { name: /^버전\(/ }).click();
  await page.getByText("1차 초안").locator("xpath=following::button[1]").click();
  await page.getByRole("button", { name: "이 버전으로 복원" }).click();
  await expect(page.getByText("이전 버전으로 복원되었습니다")).toBeVisible();
  await expect(page.locator(".ProseMirror")).not.toContainText("추가수정내용");
});

test("시나리오 E — 작성자 제출 → 검토자 수정요청 → 의견 해결 → 재검토 → 승인권자 내부 확정", async ({ page }) => {
  await login(page, E2E_RESEARCHER);
  const url = await startManuscript(page);
  await typeInEditor(page, "교차검토용 본문");
  await waitSaved(page);
  await page.locator("select").first().selectOption({ label: "E2E 테스트 검토자(reviewer)" });
  await page.getByRole("button", { name: "검토 요청", exact: true }).click();
  await expect(page.getByText("검토 요청됨")).toBeVisible();
  await logout(page);

  await login(page, E2E_REVIEWER);
  await page.goto(url);
  await page.getByRole("button", { name: "수정 요청", exact: true }).click();
  await page.getByPlaceholder("구체적인 수정 요청 사항을 입력하세요").fill("근거를 보강해주세요");
  await page.getByRole("button", { name: "수정 요청 보내기" }).click();
  await expect(page.getByText("수정 요청됨")).toBeVisible();
  await logout(page);

  await login(page, E2E_RESEARCHER);
  await page.goto(url);
  await page.getByRole("button", { name: /^검토의견\(/ }).click();
  await page.getByRole("button", { name: "해결 처리" }).click();
  await page.locator("select").first().selectOption({ label: "E2E 테스트 검토자(reviewer)" });
  await page.getByRole("button", { name: "검토 요청", exact: true }).click();
  await expect(page.getByText("검토 요청됨")).toBeVisible();
  await logout(page);

  await login(page, E2E_ADMIN);
  await page.goto(url);
  await page.getByRole("button", { name: "내부 최종 승인" }).click();
  await expect(page.getByText("내부 확정")).toBeVisible();
  // 내부 확정은 IITP 공식 선정과 별개 — IITP는 여전히 미제출이어야 한다
  await expect(page.getByText("IITP: 미제출")).toBeVisible();
});

test("시나리오 F — 동시 수정 충돌 감지 및 권한 없는 사용자 차단", async ({ browser }) => {
  const ctx1 = await newCtx(browser);
  const ctx2 = await newCtx(browser);
  const ctx3 = await newCtx(browser);
  const p1 = await ctx1.newPage();
  const p2 = await ctx2.newPage();
  const p3 = await ctx3.newPage();

  await login(p1, E2E_ADMIN);
  const url = await startManuscript(p1);
  await login(p2, E2E_ADMIN);
  await p2.goto(url);
  await p2.locator(".ProseMirror").waitFor();
  // 원고 데이터 로드가 끝난 뒤(상태 배지 표시)에 입력해야 느린 환경(CI)에서 입력이 초기화되지 않는다
  await expect(p2.getByText("초안", { exact: true })).toBeVisible();
  await expect(p2.locator(".ProseMirror")).toHaveAttribute("contenteditable", "true");

  await typeInEditor(p2, "두번째 사용자의 수정");
  await waitSaved(p2);
  await typeInEditor(p1, "첫번째 사용자의 오래된 수정");
  await expect(p1.getByText("저장 상태: 충돌 발생")).toBeVisible({ timeout: 15_000 });
  await expect(p1.getByRole("button", { name: "최신 내용 다시 불러오기" })).toBeVisible();

  // 작성자가 아닌 일반 연구원은 편집·버전저장 불가
  await login(p3, E2E_RESEARCHER);
  await p3.goto(url);
  await expect(p3.getByRole("button", { name: "주요 버전 저장" })).toBeDisabled();

  await ctx1.close();
  await ctx2.close();
  await ctx3.close();
});

test("시나리오 G — 근거 미검증 각주는 연구원이 명시적으로 확인하기 전까지 검증완료가 되지 않는다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await startManuscript(page);
  await typeInEditor(page, "출처 없는 수치 30% 증가");
  await waitSaved(page);
  await page.locator(".ProseMirror p").first().click({ clickCount: 3 });
  await page.getByRole("button", { name: "선택 영역에 근거 연결" }).click();
  await page.getByPlaceholder("원문 URL(필수)").fill("https://example.org/unverified");
  await page.getByRole("button", { name: "각주 생성" }).click();
  await expect(page.getByText("미검증")).toBeVisible();
  await expect(page.getByText("0 / 1건 확인")).toBeVisible();
  await page.getByRole("button", { name: "검증 완료로 표시" }).click();
  await expect(page.getByText("1 / 1건 확인")).toBeVisible();
});
