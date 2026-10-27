import fs from "node:fs";
import path from "node:path";
import { type Page } from "@playwright/test";
import { test, expect, API } from "./fixtures";
import { login, E2E_ADMIN } from "./helpers";

// Phase 3-8 — 안정 시연본: 모든 단계를 화면 조작으로만 진행한다(DB·API로 상태를 만들어 두지 않는다).
// 대시보드 → 우선 검토 후보 → 후보 상세(점수·근거·이슈) → 검토의견·설명 수정 → 원고 작성(원문 작업대·직접 집필·작성 점검)
// → 일반호 구성 → DOCX·PDF → 카드뉴스 → PPTX·PNG. 내려받은 파일은 test-results/phase38/ 에 저장해 별도 스크립트로 열람·서식을 검증한다.

test.setTimeout(480_000);
const OUT = path.join("test-results", "phase38");
const PREVIEW = "http://localhost:4173/index.html";

function consoleGuard(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource.*(401|404)/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

async function save(dl: import("@playwright/test").Download, name: string): Promise<Buffer> {
  fs.mkdirSync(OUT, { recursive: true });
  await dl.saveAs(path.join(OUT, name));
  return fs.readFileSync(path.join(OUT, name));
}

async function runFlow(page: Page, round: number) {
  const stamp = Date.now();
  const own = `연구원이 직접 쓴 문장 ${stamp} 입니다. 시행일은 2025.2.18.임`;

  // 1) 대시보드: 분야 건수 = 목록 건수, 자료 수 구성 설명이 보인다
  await page.goto("/dashboard");
  await expect(page.getByTestId("field-count-bcast")).toBeVisible();
  const n = Number((await page.getByTestId("field-count-bcast").textContent())?.trim());
  await page.getByTestId("field-count-bcast").click();
  await expect(page.getByTestId("result-count")).toHaveText(`총 ${n}건`);
  await page.screenshot({ path: path.join(OUT, `r${round}-1-field-list.png`) });

  // 2) 후보주제: 우선 검토 후보(최대 12건, 선별 기준·이유 표시, 공식 선정 아님)
  await page.goto("/candidates");
  const panel = page.getByTestId("priority-panel");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toContainText("IITP 공식 선정 아님");
  await expect(page.getByTestId("priority-criteria")).toContainText("개수를 채우기 위해");
  const items = page.getByTestId("priority-item");
  const cnt = await items.count();
  expect(cnt).toBeGreaterThan(0);
  expect(cnt).toBeLessThanOrEqual(12);
  await expect(items.first()).toContainText("선별 이유");
  await page.screenshot({ path: path.join(OUT, `r${round}-2-priority.png`) });
  await items.first().getByRole("link").click();

  // 3) 후보 상세: 규칙 기반 추천 평가·핵심 이슈·논쟁 가능성·근거 원문
  await expect(page.getByRole("heading", { name: /규칙 기반 추천 평가/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("issue-summary")).toContainText("규칙 기반 분석");
  await expect(page.getByTestId("dispute-label")).toContainText("논쟁 가능성");
  const rel = page.getByTestId("related-link").first();
  await expect(rel).toBeVisible();
  await page.screenshot({ path: path.join(OUT, `r${round}-3-candidate.png`) });

  // 4) 검토의견 등록 + 설명 수정·저장 → 새로고침 후 유지
  const comment = `3-8 검토의견 ${round}-${stamp}`;
  await page.getByPlaceholder("검토 의견을 입력하세요").fill(comment);
  await page.getByRole("button", { name: "등록", exact: true }).last().click();
  await expect(page.getByText(comment)).toBeVisible();
  const desc = `3-8 설명 수정 ${round}-${stamp}`;
  await page.getByLabel("후보주제 설명").fill(desc);
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("저장되었습니다")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("후보주제 설명")).toHaveValue(desc, { timeout: 15_000 });
  await expect(page.getByText(comment)).toBeVisible();

  // 5) 원고 작성 시작 → 제목 입력 → 원문 작업대(인용·발췌문) → 직접 집필 → 작성 점검
  await page.getByRole("button", { name: "원고 작성 시작" }).click();
  await page.waitForURL(/\/manuscripts\/[0-9a-f-]+$/);
  const msTitle = `E2E 3-8 원고 ${round}-${stamp}`;
  await page.locator("main input").first().fill(msTitle);
  const editor = page.locator(".ProseMirror");
  await editor.click();
  const bodySaved = page.waitForResponse((r) => r.request().method() === "PATCH" && /\/manuscripts\/[0-9a-f-]+$/.test(r.url()) && r.ok() && (r.request().postData() ?? "").includes(own.slice(0, 12)), { timeout: 20_000 });
  await page.keyboard.type(own);
  await bodySaved;
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("source-bench")).toBeVisible();
  await page.getByTestId("bench-cite").first().click();
  await expect(editor).toContainText("「");
  await page.getByTestId("bench-excerpt-toggle").first().click();
  const useExcerpt = page.getByTestId("bench-use-excerpt").first();
  if (await useExcerpt.isVisible({ timeout: 15_000 }).catch(() => false)) await useExcerpt.click(); // 전문이 없는 자료는 발췌문을 고를 수 없다(없다고 표시됨)
  await page.getByTestId("tab-lint").click();
  await expect(page.getByTestId("lint-panel")).toContainText("검증 완료로 바꾸지 않으며", { timeout: 20_000 });
  await expect(editor).toContainText(own); // 직접 쓴 문장이 유지된다
  await expect(page.getByText("저장 상태: 저장 완료")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: path.join(OUT, `r${round}-5-manuscript.png`) });

  // 6) 일반호 구성 → 발간 점검(필수 파트 경고는 그대로 노출) → DOCX·PDF
  const reportTitle = `E2E 3-8 일반호 ${round}-${stamp}`;
  await page.goto("/reports");
  await page.getByLabel("보고서 유형").selectOption("general");
  await page.getByLabel("보고서 제목").fill(reportTitle);
  await page.getByRole("button", { name: "새 보고서 만들기" }).click();
  await page.waitForURL(/\/reports\/[0-9a-f-]+$/);
  await page.getByLabel("key_issue 원고 선택").selectOption({ index: 1 }); // 최근 수정순 — 방금 쓴 원고
  await page.getByRole("button", { name: "원고 배치" }).first().click();
  await expect(page.getByRole("link", { name: msTitle })).toBeVisible();
  await expect(page.getByText("IITP 공식 확인 전", { exact: true })).toBeVisible();
  const [docx] = await Promise.all([page.waitForEvent("download", { timeout: 120_000 }), page.getByRole("button", { name: "DOCX 다운로드" }).click()]);
  expect((await save(docx, `r${round}-report.docx`)).subarray(0, 2).toString()).toBe("PK");
  const [pdf] = await Promise.all([page.waitForEvent("download", { timeout: 180_000 }), page.getByRole("button", { name: "PDF 다운로드" }).click()]);
  expect((await save(pdf, `r${round}-report.pdf`)).subarray(0, 4).toString()).toBe("%PDF");
  await page.screenshot({ path: path.join(OUT, `r${round}-6-report.png`) });

  // 7) 카드뉴스: 보고서 문장으로 생성 → PPTX·PNG
  await page.goto("/card-news");
  await page.getByRole("radio", { name: "기존 보고서에서 만들기" }).check();
  await page.getByLabel("원본 보고서").selectOption({ label: reportTitle });
  await page.getByLabel(/^문장 선택: /).first().check();
  await page.getByRole("radio", { name: /^A\./ }).check();
  await page.getByLabel("카드뉴스 제목").fill(`E2E 3-8 카드뉴스 ${round}-${stamp}`);
  await page.getByRole("button", { name: "카드뉴스 만들기" }).click();
  await page.waitForURL(/\/card-news\/[0-9a-f-]+$/);
  await page.getByRole("button", { name: "점검·출력" }).click();
  const [pptx] = await Promise.all([page.waitForEvent("download", { timeout: 120_000 }), page.getByRole("button", { name: "PPTX 다운로드" }).click()]);
  expect((await save(pptx, `r${round}-cards.pptx`)).subarray(0, 2).toString()).toBe("PK");
  await page.getByLabel("PNG 해상도").selectOption("1000");
  const [zip] = await Promise.all([page.waitForEvent("download", { timeout: 240_000 }), page.getByRole("button", { name: "PNG(ZIP) 다운로드" }).click()]);
  expect((await save(zip, `r${round}-cards_png.zip`)).subarray(0, 2).toString()).toBe("PK");
  await page.screenshot({ path: path.join(OUT, `r${round}-7-cardnews.png`) });
}

for (const round of [1, 2]) {
  test(`3-8 통합 시연 ${round}회차 — 대시보드→우선 검토 후보→후보 검토→원고 작성→점검→DOCX·PDF→카드뉴스 PPTX·PNG (화면 조작만, 콘솔 오류 0)`, async ({ page }) => {
    const errors = consoleGuard(page);
    await login(page, E2E_ADMIN);
    // 이 시나리오는 실제 수집 자료가 있는 DB에서 의미가 있다. 깨끗한 CI 고정 데이터에는 우선 검토 기준(점수·공식 링크·근거)을 충족하는 후보가 없어 건너뛴다
    // (우선 검토 후보 선별 로직은 pytest 와 개발 DB E2E 로 검증한다).
    const priority = await page.evaluate(async () => (await fetch((window as unknown as { E2E_API: string }).E2E_API + "/candidates/priority", { credentials: "include" })).json());
    test.skip(!priority.items || priority.items.length === 0, "기준을 충족하는 우선 검토 후보가 없는 데이터베이스(CI 고정 데이터)");
    await runFlow(page, round);
    expect(errors, errors.join("\n")).toEqual([]);
  });
}

test("3-8 정합 — 대시보드 자료 수 구성 = 전체 수집 건수, 분야 합계 + 주 분야 미지정 = 분류 완료", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const r = await page.evaluate(async () => (await fetch((window as unknown as { E2E_API: string }).E2E_API + "/dashboard/summary", { credentials: "include" })).json());
  expect(r.total_documents).toBe(r.matched_documents + r.low_relevance_documents + r.pending_review_documents + r.unclassified_documents);
  expect(r.matched_documents).toBe(r.by_field.reduce((s: number, f: any) => s + f.document_count, 0) + r.matched_without_field);
  expect(r.matched_without_field).toBe(0); // 시연 데이터에는 주 분야가 비어 있는 분류 완료 자료가 없다
});

test("3-8 공개 /preview/ — 우선 검토 후보·자료 수 구성 안내·두 화면 구분 안내", async ({ page }) => {
  await page.goto(`${PREVIEW}#/`);
  await expect(page.getByTestId("reconcile")).toContainText("분류 보류");
  await expect(page.getByTestId("reconcile")).toContainText("재분류하지 않았습니다");
  await page.goto(`${PREVIEW}#/candidates`);
  const panel = page.getByTestId("priority-panel");
  await expect(panel).toContainText("IITP 공식 선정 아님");
  const n = await page.getByTestId("priority-item").count();
  expect(n).toBeGreaterThan(0);
  expect(n).toBeLessThanOrEqual(12);
  await page.goto(`${PREVIEW}#/guide`);
  await expect(page.getByTestId("demo-versions")).toContainText("기존 시연 화면");
  const raw = await (await page.request.get("http://localhost:4173/data/snapshot.json")).text();
  expect(raw).not.toMatch(/[\w.+-]+@[\w-]+\.[\w.]+/);
  expect(raw).not.toMatch(/sk-ant-|sk-proj-|ai_results|모의 응답/i);
});

for (const vp of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
  test(`3-8 화면 점검 ${vp.width}×${vp.height} — 주요 화면에 가로 넘침·오류 문구·무한 로딩이 없다`, async ({ page }) => {
    const errors = consoleGuard(page);
    await page.setViewportSize(vp);
    await login(page, E2E_ADMIN);
    for (const href of ["/dashboard", "/guide", "/documents?field_code=bcast", "/issues", "/candidates", "/manuscripts", "/reports", "/card-news", "/followups"]) {
      await page.goto(href);
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText("불러오는 중...")).toHaveCount(0, { timeout: 20_000 });
      await expect(page.getByText("Application error")).toHaveCount(0);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(over, `${href} 가로 넘침 ${over}px`).toBeLessThanOrEqual(1);
      if (href === "/dashboard" || href === "/candidates") await page.screenshot({ path: path.join(OUT, `ui-${vp.width}-${href.slice(1)}.png`) });
    }
    expect(errors, errors.join("\n")).toEqual([]);
  });
}
