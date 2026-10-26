import fs from "node:fs";
import { test, expect, type Page } from "@playwright/test";
import { login, logout, E2E_ADMIN, E2E_RESEARCHER, E2E_REVIEWER } from "./helpers";

test.setTimeout(300_000);

async function startManuscript(page: Page, uniqueTitle: string, bodyText: string): Promise<void> {
  await page.goto("/candidates");
  await page.locator("table tbody tr td a").first().click();
  await page.getByRole("button", { name: "원고 작성 시작" }).click();
  await page.waitForURL(/\/manuscripts\/[0-9a-f-]+$/);
  await page.locator("main input").first().fill(uniqueTitle);
  await page.locator(".ProseMirror").click();
  const bodySaved = page.waitForResponse(
    (r) => r.request().method() === "PATCH" && /\/manuscripts\/[0-9a-f-]+$/.test(r.url()) && r.ok()
      && (r.request().postData() ?? "").includes(bodyText.slice(0, 12)),
    { timeout: 20_000 },
  );
  await page.keyboard.type(bodyText);
  await bodySaved;
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
}

async function makeReportWith(page: Page, reportTitle: string) {
  await page.goto("/reports");
  await page.getByLabel("보고서 제목").fill(reportTitle);
  await page.getByRole("button", { name: "새 보고서 만들기" }).click();
  await page.waitForURL(/\/reports\/[0-9a-f-]+$/);
  await page.getByLabel("key_issue 원고 선택").selectOption({ index: 1 }); // 최근 수정순 — 방금 만든 원고
  await page.getByRole("button", { name: "원고 배치" }).first().click();
  await expect(page.locator("main").getByRole("link").first()).toBeVisible();
}

async function newManualCardNews(page: Page, title: string, template = "A") {
  await page.goto("/card-news");
  await page.getByRole("radio", { name: "새로 직접 작성" }).check();
  await page.getByRole("radio", { name: new RegExp(`^${template}\\.`) }).check();
  await page.getByLabel("카드뉴스 제목").fill(title);
  await page.getByRole("button", { name: "카드뉴스 만들기" }).click();
  await page.waitForURL(/\/card-news\/[0-9a-f-]+$/);
  return page.url();
}

async function waitSaved(page: Page) {
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
}

async function fillA(page: Page) {
  await page.getByRole("button", { name: /^카드 1 / }).click();
  await page.getByLabel("표지 제목", { exact: true }).fill("E2E 전기차 안전기준 동향");
  await page.getByLabel("표지 제목", { exact: true }).blur();
  await waitSaved(page);
  await page.getByRole("button", { name: /^카드 2 / }).click();
  await page.getByLabel("카드 제목", { exact: true }).fill("추진 경과");
  await page.getByLabel("핵심 내용 1", { exact: true }).fill("최종 규정은 2025.2.18.부터 시행됨");
  await page.getByLabel("핵심 내용 1", { exact: true }).blur();
  await page.getByLabel("출처", { exact: true }).fill("NHTSA");
  await page.getByLabel("출처", { exact: true }).blur();
  await waitSaved(page);
}

test("시나리오 K — 보고서에서 카드뉴스 생성 → 편집·저장·새로고침·재로그인 유지 → 카드 조작·템플릿 변경 → 근거 검증", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const stamp = Date.now();
  const sentence = `카드뉴스에 옮길 핵심 문장 ${stamp} 입니다 시행일은 2025.2.18.임`;
  await startManuscript(page, `E2E카드원고${stamp}`, sentence);
  await makeReportWith(page, `E2E 카드용 보고서 ${stamp}`);

  await page.goto("/card-news");
  await page.getByRole("radio", { name: "기존 보고서에서 만들기" }).check();
  await page.getByLabel("원본 보고서").selectOption({ label: `E2E 카드용 보고서 ${stamp}` });
  await page.getByLabel(/^문장 선택: /).first().check();
  await expect(page.getByText(/선택한 1개 문장/)).toBeVisible();
  await page.getByRole("radio", { name: /^A\./ }).check();
  await page.getByLabel("카드뉴스 제목").fill(`E2E 카드뉴스 ${stamp}`);
  await page.getByRole("button", { name: "카드뉴스 만들기" }).click();
  await page.waitForURL(/\/card-news\/[0-9a-f-]+$/);
  const url = page.url();

  // 5장(표지·본문 3·마무리), 보고서 문장이 첫 본문 카드의 핵심 내용 1에 들어가 있다
  await expect(page.getByRole("button", { name: /^카드 \d+ / })).toHaveCount(5);
  await page.getByRole("button", { name: /^카드 2 / }).click();
  await expect(page.getByLabel("핵심 내용 1", { exact: true })).toHaveValue(sentence);
  await expect(page.getByText("근거 없음").first()).toBeVisible(); // 원고 각주가 없는 문장은 근거 없음으로 표시된다
  await expect(page.getByRole("img", { name: "카드 2 미리보기" })).toContainText(String(stamp));

  // 편집 → 자동저장 → 새로고침·재로그인 후에도 유지
  await page.getByLabel("핵심 내용 2", { exact: true }).fill("연구원이 직접 입력한 두 번째 핵심 내용");
  await page.getByLabel("핵심 내용 2", { exact: true }).blur();
  await waitSaved(page);
  await page.reload();
  await page.getByRole("button", { name: /^카드 2 / }).click();
  await expect(page.getByLabel("핵심 내용 2", { exact: true })).toHaveValue("연구원이 직접 입력한 두 번째 핵심 내용");
  await logout(page);
  await login(page, E2E_ADMIN);
  await page.goto(url);
  await page.getByRole("button", { name: /^카드 2 / }).click();
  await expect(page.getByLabel("핵심 내용 2", { exact: true })).toHaveValue("연구원이 직접 입력한 두 번째 핵심 내용");

  // 카드 추가·복제·삭제·순서 변경
  await page.getByRole("button", { name: "추가", exact: true }).click();
  await expect(page.getByRole("button", { name: /^카드 \d+ / })).toHaveCount(6);
  await page.getByRole("button", { name: "복제", exact: true }).click();
  await expect(page.getByRole("button", { name: /^카드 \d+ / })).toHaveCount(7);
  await page.getByRole("button", { name: "삭제", exact: true }).click();
  await expect(page.getByRole("button", { name: /^카드 \d+ / })).toHaveCount(6);
  await page.getByRole("button", { name: /^카드 2 / }).click();
  await page.getByRole("button", { name: "카드 아래로" }).click();
  await waitSaved(page);
  await page.getByRole("button", { name: "카드 위로" }).click(); // 순서를 원래대로 되돌린다
  await waitSaved(page);

  // 템플릿 변경(A → B): 핵심 내용이 타임라인 1단계로 옮겨지고 날짜는 문장에서 읽은 값만 들어간다
  await page.getByLabel("디자인 템플릿").selectOption("B");
  await expect(page.getByText(/템플릿을 바꿨습니다/)).toBeVisible();
  await page.getByRole("button", { name: /^카드 \d+ \(본문\)/ }).first().click();
  await expect(page.getByLabel("1단계 내용", { exact: true })).toHaveValue(/카드뉴스에 옮길 핵심 문장/);
  await expect(page.getByLabel("1단계 날짜", { exact: true })).toHaveValue("2025.2.18.");
  await page.getByLabel("디자인 템플릿").selectOption("A");

  // 근거 연결 → 직접 검증 → 수정하면 재검증 필요
  await page.getByRole("button", { name: /^카드 \d+ \(본문\)/ }).first().click();
  await page.getByRole("button", { name: "원문 근거" }).click();
  await page.getByLabel("핵심 내용 1 근거 URL").fill("https://www.federalregister.gov/documents/test");
  await page.getByLabel("핵심 내용 1 근거 기관").fill("NHTSA");
  await page.getByRole("button", { name: "근거 연결" }).first().click();
  await expect(page.getByText("근거를 연결했습니다(아직 검증 전)")).toBeVisible();
  await page.getByRole("button", { name: "검증 완료로 표시" }).first().click();
  await expect(page.getByText("검증 완료", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "내용·디자인" }).click();
  await page.getByLabel("핵심 내용 1", { exact: true }).fill(sentence + " (수정)");
  await page.getByLabel("핵심 내용 1", { exact: true }).blur();
  await waitSaved(page);
  await expect(page.getByText("수정됨·재검증 필요").first()).toBeVisible();
});

test("시나리오 L — PPTX·PNG 실제 파일 다운로드, PNG 해상도, 출력 이력·재다운로드", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const stamp = Date.now();
  await newManualCardNews(page, `E2E 출력 카드뉴스 ${stamp}`, "A");
  await fillA(page);

  await page.getByRole("button", { name: "점검·출력" }).click();
  const [pptx] = await Promise.all([
    page.waitForEvent("download", { timeout: 120_000 }),
    page.getByRole("button", { name: "PPTX 다운로드" }).click(),
  ]);
  expect(pptx.suggestedFilename()).toMatch(/\.pptx$/);
  const pptxBytes = fs.readFileSync((await pptx.path())!);
  expect(pptxBytes.subarray(0, 2).toString()).toBe("PK"); // OOXML 패키지
  expect(pptxBytes.length).toBeGreaterThan(8_000);
  await expect(page.getByText(/PPTX를 생성하고 내려받았습니다/)).toBeVisible();

  await page.getByLabel("PNG 해상도").selectOption("1000");
  const [zip] = await Promise.all([
    page.waitForEvent("download", { timeout: 240_000 }),
    page.getByRole("button", { name: "PNG(ZIP) 다운로드" }).click(),
  ]);
  expect(zip.suggestedFilename()).toMatch(/_png\.zip$/);
  expect(fs.readFileSync((await zip.path())!).subarray(0, 2).toString()).toBe("PK");
  await expect(page.getByText(/PNG 5장\(1000×2232px\)/)).toBeVisible();
  const gallery = page.getByRole("img", { name: /^PNG \d번 카드/ });
  await expect(gallery).toHaveCount(5);
  const sizes = await gallery.evaluateAll((imgs) => (imgs as HTMLImageElement[]).map((i) => [i.naturalWidth, i.naturalHeight]));
  for (const [w, h] of sizes) {
    expect(Math.min(w, h)).toBeGreaterThanOrEqual(1000);
    expect(Math.abs(w / h - 7 / 15.62)).toBeLessThan(0.01); // PPTX와 같은 비율
  }

  // 출력 이력에 두 파일이 남고 재다운로드할 수 있다
  await expect(page.getByRole("button", { name: "재다운로드" })).toHaveCount(2);
  const [again] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "재다운로드" }).first().click()]);
  expect(fs.readFileSync((await again.path())!).length).toBeGreaterThan(1000);
});

test("시나리오 M — 검토 요청 → 수정 요청 → 의견 해결 → 승인권자 내부 확정(예외 사유) → 확정 후 수정 차단·새 수정 버전·권한", async ({ page }) => {
  await login(page, E2E_RESEARCHER);
  const stamp = Date.now();
  const url = await newManualCardNews(page, `E2E 승인 카드뉴스 ${stamp}`, "A");
  await fillA(page);
  await page.getByRole("button", { name: "검토·승인" }).click();
  await page.getByLabel("검토자 선택").selectOption({ label: "E2E 테스트 검토자(reviewer)" });
  await page.getByRole("button", { name: "검토 요청", exact: true }).click();
  await expect(page.getByText("검토 요청됨").first()).toBeVisible();
  // 연구원에게는 내부 확정 버튼이 없다
  await expect(page.getByRole("button", { name: "내부 확정" })).toHaveCount(0);
  await logout(page);

  await login(page, E2E_REVIEWER);
  await page.goto(url);
  await page.getByRole("button", { name: "검토·승인" }).click();
  await page.getByLabel("수정 요청 사유").fill("출처 표기를 보강해주세요");
  await page.getByRole("button", { name: "수정 요청 보내기" }).click();
  await expect(page.getByText("수정 요청됨").first()).toBeVisible();
  await logout(page);

  await login(page, E2E_RESEARCHER);
  await page.goto(url);
  await page.getByRole("button", { name: "검토·승인" }).click();
  await page.getByRole("button", { name: "해결 처리" }).click();
  await page.getByLabel("검토자 선택").selectOption({ label: "E2E 테스트 검토자(reviewer)" });
  await page.getByRole("button", { name: "검토 요청", exact: true }).click();
  await expect(page.getByText("검토 요청됨").first()).toBeVisible();
  await logout(page);

  // 승인권자(관리자): 미검증 근거·미완성 요소가 있어 사유 없이는 확정되지 않는다
  await login(page, E2E_ADMIN);
  await page.goto(url);
  await page.getByRole("button", { name: "검토·승인" }).click();
  await page.getByRole("button", { name: "내부 확정" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "필수 점검을 통과하지 못해" })).toBeVisible();
  await page.getByLabel("예외 승인 사유").fill("E2E 내부 점검용 예외 확정");
  await page.getByRole("button", { name: "내부 확정" }).click();
  await expect(page.getByText("내부 확정되었습니다(IITP 공식 확인 아님)")).toBeVisible();
  await expect(page.getByText("IITP 공식 확인 전", { exact: true })).toBeVisible(); // 내부 확정 ≠ IITP 확인

  // 확정 후에는 수정할 수 없고, 새 수정 버전(복사본)을 만들 수 있다
  await page.getByRole("button", { name: "내용·디자인" }).click();
  await page.getByRole("button", { name: /^카드 2 / }).click();
  await expect(page.getByLabel("카드 제목", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "검토·승인" }).click();
  await page.getByRole("button", { name: "새 수정 버전 만들기" }).click();
  await expect(page).not.toHaveURL(url);
  await page.waitForURL(/\/card-news\/[0-9a-f-]+$/);
  await expect(page.getByLabel("카드뉴스 제목")).toHaveValue(/\(수정본\)/);
  await expect(page.getByText("작성 중", { exact: true }).first()).toBeVisible();
});
