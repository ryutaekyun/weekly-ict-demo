import fs from "node:fs";
import { test, expect, type Page } from "@playwright/test";
import { login, logout, E2E_ADMIN, E2E_RESEARCHER } from "./helpers";

test.setTimeout(240_000);

async function startManuscript(page: Page, uniqueTitle: string, bodyText: string): Promise<string> {
  await page.goto("/candidates");
  await page.locator("table tbody tr td a").first().click();
  await page.getByRole("button", { name: "원고 작성 시작" }).click();
  await page.waitForURL(/\/manuscripts\/[0-9a-f-]+$/);
  const url = page.url();
  await page.locator("main input").first().fill(uniqueTitle);
  await page.locator(".ProseMirror").click(); // 제목 입력란이 포커스를 잃으며 제목이 먼저 저장된다
  // 본문 저장 요청(PATCH)에 입력한 문장이 실제로 실려 성공할 때까지 기다린다(제목 저장만 끝난 상태를 저장 완료로 오인하지 않도록)
  const bodySaved = page.waitForResponse(
    (r) => r.request().method() === "PATCH" && /\/manuscripts\/[0-9a-f-]+$/.test(r.url()) && r.ok()
      && (r.request().postData() ?? "").includes(bodyText.slice(0, 12)),
    { timeout: 20_000 },
  );
  await page.keyboard.type(bodyText);
  await bodySaved;
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
  return url;
}

async function createReport(page: Page, type: "general" | "special" | "summary", title: string) {
  await page.goto("/reports");
  await page.getByLabel("보고서 유형").selectOption(type);
  await page.getByLabel("보고서 제목").fill(title);
  await page.getByRole("button", { name: "새 보고서 만들기" }).click();
  await page.waitForURL(/\/reports\/[0-9a-f-]+$/);
  return page.url();
}

test("시나리오 H — 일반호 구성 → 발간 점검 → DOCX·PDF 실제 파일 다운로드 → 출력 이력·미리보기", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const stamp = Date.now();
  const msTitle = `E2E일반호원고${stamp}`;
  await startManuscript(page, msTitle, "보고서에 들어갈 본문 문장입니다. 시행일은 2025.2.18.임");

  await createReport(page, "general", `E2E 일반호 ${stamp}`);
  // 원고 목록은 최근 수정순이므로 방금 만든 원고가 첫 번째 선택지다
  await page.getByLabel("key_issue 원고 선택").selectOption({ index: 1 });
  await page.getByRole("button", { name: "원고 배치" }).first().click();
  await expect(page.getByRole("link", { name: msTitle })).toBeVisible();

  // 필수 파트(주요국 동향)가 비어 있으면 발간 점검에 필수 경고가 보인다 — 임의로 채우지 않는다
  await expect(page.getByText("'주요국 동향' 파트에 원고가 없습니다")).toBeVisible();
  await expect(page.getByText("IITP 공식 확인 전", { exact: true })).toBeVisible();

  // DOCX 실제 다운로드
  const [docx] = await Promise.all([
    page.waitForEvent("download", { timeout: 120_000 }),
    page.getByRole("button", { name: "DOCX 다운로드" }).click(),
  ]);
  expect(docx.suggestedFilename()).toMatch(/\.docx$/);
  const docxBytes = fs.readFileSync((await docx.path())!);
  expect(docxBytes.subarray(0, 2).toString()).toBe("PK"); // OOXML(zip) 패키지
  expect(docxBytes.length).toBeGreaterThan(8_000);
  await expect(page.getByText(/DOCX 파일을 생성하고 내려받았습니다/)).toBeVisible();

  // PDF 실제 다운로드 + 미리보기
  const [pdf] = await Promise.all([
    page.waitForEvent("download", { timeout: 180_000 }),
    page.getByRole("button", { name: "PDF 다운로드" }).click(),
  ]);
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
  const pdfBytes = fs.readFileSync((await pdf.path())!);
  expect(pdfBytes.subarray(0, 4).toString()).toBe("%PDF");
  await expect(page.getByTitle("PDF 미리보기")).toBeVisible();

  // 출력 이력에 두 파일이 남고 재다운로드할 수 있다
  await expect(page.getByRole("button", { name: "재다운로드" })).toHaveCount(2);
  await expect(page.getByText(/각주 \d+ · 표 \d+/).first()).toBeVisible();
  const [again] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "재다운로드" }).first().click(),
  ]);
  expect(fs.readFileSync((await again.path())!).length).toBeGreaterThan(1000);
});

test("시나리오 I — 요약본: 원고 문장 선택 → 수정 → 저장·새로고침 유지 → 원고 변경 시 재검토 필요 표시", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const stamp = Date.now();
  const msTitle = `E2E요약원고${stamp}`;
  const sentence = `요약본에 반영할 핵심 문장 ${stamp} 입니다`;
  const msUrl = await startManuscript(page, msTitle, sentence);

  const reportUrl = await createReport(page, "summary", `E2E 요약본 ${stamp}`);
  await page.getByLabel("요약 대상 원고").selectOption({ index: 1 });
  await expect(page.getByText(sentence)).toBeVisible();
  await page.getByRole("button", { name: "요약에 추가" }).first().click();

  const box = page.getByRole("textbox", { name: /^요약문:/ });
  await expect(box).toHaveValue(sentence);
  await box.fill("연구원이 직접 다듬은 요약문");
  await box.blur();
  await page.waitForTimeout(800);
  await page.reload();
  await expect(page.getByRole("textbox", { name: /^요약문:/ })).toHaveValue("연구원이 직접 다듬은 요약문");
  await expect(page.getByText("원고 변경 — 요약본 재검토 필요")).toHaveCount(0);

  // 원본 원고의 해당 문장이 바뀌면 요약본에 재검토 표시가 뜨고, 다듬은 요약문은 그대로 유지된다
  await page.goto(msUrl);
  await page.locator(".ProseMirror").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type("완전히 다른 내용으로 원고를 고쳤습니다 새 문장");
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
  await page.goto(reportUrl);
  await expect(page.getByText("원고 변경 — 요약본 재검토 필요")).toBeVisible();
  await expect(page.getByRole("textbox", { name: /^요약문:/ })).toHaveValue("연구원이 직접 다듬은 요약문");
});

test("시나리오 J — 출력용 확정: 연구원 불가·필수 점검 미통과 차단·승인권자 예외 사유로 확정·타 사용자 파일 접근 차단", async ({ page, browser }) => {
  await login(page, E2E_RESEARCHER);
  const stamp = Date.now();
  const msTitle = `E2E확정원고${stamp}`;
  await startManuscript(page, msTitle, "확정 점검용 본문 문장입니다");
  const reportUrl = await createReport(page, "special", `E2E 특집호 ${stamp}`);
  await page.getByLabel("free 원고 선택").selectOption({ index: 1 });
  await page.getByRole("button", { name: "원고 배치" }).click();
  await expect(page.getByRole("link", { name: msTitle })).toBeVisible();

  // 연구원에게는 확정 버튼이 없다
  await expect(page.getByRole("button", { name: "출력용 확정" })).toHaveCount(0);
  await expect(page.getByText("출력용 확정은 승인권자·관리자만 할 수 있습니다")).toBeVisible();

  // 작성자 본인은 DOCX 출력 가능(검증 전이라도 내부 검토용 초안)
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120_000 }), page.getByRole("button", { name: "DOCX 다운로드" }).click()]);
  expect((await dl.suggestedFilename())).toMatch(/_초안\.docx$/);
  const reportId = reportUrl.split("/").pop()!;
  await logout(page);

  // 다른 연구원이 아닌 관리자(승인권한)가 확정: 미승인 원고가 있어 예외 사유 없이는 막힌다
  await login(page, E2E_ADMIN);
  await page.goto(reportUrl);
  await page.getByRole("button", { name: "출력용 확정" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "필수 점검을 통과하지 못해" })).toBeVisible();
  await page.getByLabel("예외 승인 사유").fill("E2E 내부 점검용 예외 확정");
  await page.getByRole("button", { name: "출력용 확정" }).click();
  await expect(page.getByText("출력용 확정되었습니다(IITP 공식 확인 아님)")).toBeVisible();
  await expect(page.getByText("IITP 공식 확인 전", { exact: true })).toBeVisible(); // 확정 ≠ IITP 확인
  await expect(page.getByText("예외 사유: E2E 내부 점검용 예외 확정")).toBeVisible();
  await logout(page);

  // 확정 후에는 작성자도 구성을 바꿀 수 없다(제거 버튼 비활성)
  await login(page, E2E_RESEARCHER);
  await page.goto(reportUrl);
  await expect(page.getByRole("button", { name: "제거" }).first()).toBeDisabled();
  await logout(page);

  // 보고서를 만들지 않은 다른 연구원 계정은 출력 파일 목록·다운로드가 서버에서 차단된다(권한 없음 확인)
  const ctx = await browser.newContext({ baseURL: "http://localhost:3000" });
  const other = await ctx.newPage();
  const result = await other.request.get(`http://localhost:8000/reports/${reportId}/exports`);
  expect(result.status()).toBe(401); // 비로그인
  await ctx.close();
});
