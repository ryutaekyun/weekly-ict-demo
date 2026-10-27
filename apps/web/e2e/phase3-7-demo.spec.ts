import { test, expect, type Page } from "@playwright/test";
import { login, E2E_ADMIN } from "./helpers";

// Phase 3-7 — 무료 시연 플랫폼: 분야 탐색 → 원문 → 이슈 → 후보 검토 → 직접 집필(원문 작업대·작성 점검) → 공개 /preview/ 읽기 전용 화면, 메뉴 전수 점검.
// 서버는 CI/로컬 모두 모의 공급자(AI_PROVIDER=mock)이며 유료 AI 호출은 코드 수준으로 차단되어 있다.

const PREVIEW = "http://localhost:4173/index.html";

async function api<T = any>(page: Page, method: string, path: string, body?: unknown): Promise<{ status: number; json: T }> {
  return page.evaluate(async ({ method, path, body }) => {
    const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1];
    const res = await fetch(`http://localhost:8000${path}`, {
      method, credentials: "include",
      headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": decodeURIComponent(csrf) } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    return { status: res.status, json: await res.json().catch(() => null) };
  }, { method, path, body });
}

async function multiDocIssue(page: Page): Promise<string> {
  const list = await api(page, "GET", "/issues?page_size=200");
  const issues: any[] = Array.isArray(list.json) ? list.json : list.json.items;
  for (const it of issues.filter((i) => (i.document_count ?? 2) >= 2).slice(0, 60)) {
    const est = await api(page, "POST", "/ai/estimate", { kind: "issue", target_id: it.id });
    if (est.status === 200 && est.json.documents.length >= 2) return it.id;
  }
  throw new Error("원문 전문이 있는 복수 문서 이슈를 찾지 못함");
}

test("3-7 A·F·G — 대시보드 분야 → 자료 목록(건수 일치) → 제목 클릭 새 탭 원문 → 상세 분석 → 이슈·후보 확인", async ({ page, context }) => {
  await login(page, E2E_ADMIN);
  await page.goto("/dashboard");
  const count = page.getByTestId("field-count-ai");
  await expect(count).toBeVisible();
  const n = Number((await count.textContent())?.trim());
  await count.click();
  await expect(page).toHaveURL(/field_code=ai/);
  await expect(page.getByTestId("result-count")).toHaveText(`총 ${n}건`); // 대시보드 건수 = 목록 건수(실제 조회 결과)
  const link = page.getByTestId("news-link").first().locator("a");
  await expect(link).toHaveAttribute("target", "_blank");
  const href = await link.getAttribute("href");
  expect(href).not.toMatch(/^https?:\/\/[^/]+\/?$/); // 기관 홈페이지가 아니라 개별 원문 주소
  const popup = context.waitForEvent("page");
  await link.click();
  await (await popup).close();
  await page.getByRole("link", { name: /^상세 분석/ }).first().click();
  await expect(page.getByTestId("detail-origin-link")).toBeVisible();
  await expect(page.getByTestId("ai-free-note").or(page.getByTestId("ai-mock-banner")).first()).toBeVisible(); // 규칙 기반 안내 또는 모의 표시
  // 후보주제 상세: 점수·근거·논쟁 가능성·이슈 요약
  const issue = await multiDocIssue(page);
  const detail = await api(page, "GET", `/issues/${issue}`);
  const cand = await api(page, "POST", "/candidates", { field_code: detail.json.field_code ?? "ai", title: `3-7 후보 ${Date.now()}`, issue_cluster_id: issue, source_document_id: detail.json.members[0].document_id });
  await page.goto(`/candidates/${cand.json.id}`);
  await expect(page.getByTestId("issue-summary")).toContainText("규칙 기반 분석");
  await expect(page.getByTestId("dispute-label")).toContainText("논쟁 가능성");
  await expect(page.getByTestId("related-link").first()).toBeVisible();
});

test("3-7 H·4 — 후보 상세: 분야 수정·추가 조사 필요 상태·검토의견·근거 원문 제외/복원이 저장되고 새로고침 후 유지된다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const issue = await multiDocIssue(page);
  const detail = await api(page, "GET", `/issues/${issue}`);
  const cand = await api(page, "POST", "/candidates", { field_code: detail.json.field_code ?? "ai", title: `3-7 검토 후보 ${Date.now()}`, issue_cluster_id: issue, source_document_id: detail.json.members[0].document_id });
  await page.goto(`/candidates/${cand.json.id}`);
  await page.getByLabel("후보주제 관련 분야").selectOption("sec");
  const newTitle = `3-7 수정된 제목 ${Date.now()}`;
  await page.getByLabel("후보주제 제목", { exact: true }).fill(newTitle);
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("저장되었습니다")).toBeVisible();
  await page.getByRole("button", { name: "추가 조사 필요로 변경" }).click();
  await expect(page.locator("span.pill").filter({ hasText: "추가 조사 필요" }).first()).toBeVisible();
  // 근거 원문 제외 → 복원
  const before = await page.getByTestId("related-link").count();
  await page.getByTestId("evidence-exclude").first().click();
  await expect(page.getByText("근거에서 제외했습니다")).toBeVisible();
  await expect(page.getByTestId("excluded-docs")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("후보주제 제목", { exact: true })).toHaveValue(newTitle);
  await expect(page.getByLabel("후보주제 관련 분야")).toHaveValue("sec");
  await expect(page.getByTestId("related-link")).toHaveCount(before - 1);
  await page.getByTestId("excluded-docs").getByRole("button", { name: "복원" }).first().click();
  await expect(page.getByTestId("related-link")).toHaveCount(before);
});

test("3-7 I·5 — 직접 집필: 원문 작업대(인용·발췌문)·목차 템플릿·제목 불러오기·작성 점검, 기존 문장은 덮어쓰이지 않고 각주는 미검증", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const issue = await multiDocIssue(page);
  const detail = await api(page, "GET", `/issues/${issue}`);
  const cand = await api(page, "POST", "/candidates", { field_code: detail.json.field_code ?? "ai", title: `3-7 집필 후보 ${Date.now()}`, issue_cluster_id: issue, source_document_id: detail.json.members[0].document_id });
  const ms = await api(page, "POST", "/manuscripts", { manuscript_type: "key_issue", title: "임시 제목", candidate_id: cand.json.id });
  const own = "연구원이 직접 쓴 첫 문장임";
  const body = JSON.stringify({ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: own }] }] });
  expect((await api(page, "PATCH", `/manuscripts/${ms.json.id}`, { body_json: body, body: own, lock_version: ms.json.lock_version })).status).toBe(200);

  await page.goto(`/manuscripts/${ms.json.id}`);
  await expect(page.getByTestId("source-bench")).toBeVisible(); // 왼쪽 원문·근거 작업대 / 가운데 편집기 / 오른쪽 검토 패널
  await expect(page.getByTestId("bench-doc").first()).toBeVisible();
  const editor = page.locator(".ProseMirror");
  await editor.getByText(own).click();
  // 인용 넣기: 제목·기관·발표일 자동 인용 + 미검증 각주
  await page.getByTestId("bench-cite").first().click();
  await expect(editor).toContainText("「");
  await expect(editor).toContainText(own); // 기존 문장 유지
  // 발췌문 고르기 → 원문 그대로 삽입
  await page.getByTestId("bench-excerpt-toggle").first().click();
  const firstUse = page.getByTestId("bench-use-excerpt").first();
  await expect(firstUse).toBeVisible();
  await firstUse.click();
  await expect(page.getByRole("status").filter({ hasText: "발췌문을 넣었습니다" })).toBeVisible();
  // 목차 템플릿 + 제목 불러오기
  await page.getByTestId("insert-template").click();
  await expect(editor).toContainText("Ⅰ. 배경과 주요 내용");
  await expect(editor).toContainText(own);
  await page.getByTestId("load-title").click();
  await expect(page.locator('input[value^="3-7 집필 후보"]')).toBeVisible({ timeout: 15_000 });
  // 각주는 모두 미검증(원문을 가져왔다고 검증된 것이 아니다)
  const fns = await api(page, "GET", `/manuscripts/${ms.json.id}/footnotes`);
  expect(fns.json.length).toBeGreaterThanOrEqual(2);
  expect(fns.json.every((f: any) => f.verification_status === "not_verified")).toBe(true);
  // 작성 점검
  await page.getByTestId("tab-lint").click();
  const panel = page.getByTestId("lint-panel");
  await expect(panel.getByTestId("lint-warning").first()).toBeVisible({ timeout: 15_000 });
  await expect(panel).toContainText("근거 미검증");
  await expect(panel).toContainText("검증 완료로 바꾸지 않으며");
  // 새로고침 후에도 유지
  await page.reload();
  await expect(page.locator(".ProseMirror")).toContainText(own);
  await expect(page.locator(".ProseMirror")).toContainText("Ⅰ. 배경과 주요 내용");
});

test("3-7 10 — 메뉴·상세 화면 전수 점검: 모든 메뉴가 열리고 콘솔 오류·무한 로딩·'Application error'가 없다", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource.*(401|404)/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  await login(page, E2E_ADMIN);
  const nav = ["/dashboard", "/guide", "/documents", "/issues", "/candidates", "/manuscripts", "/reports", "/card-news", "/followups", "/journal", "/sources", "/settings"];
  for (const href of nav) await expect(page.locator(`a[href="${href}"]`).first()).toBeVisible(); // 메뉴에 모두 노출
  for (const href of nav) {
    await page.goto(href);
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Application error")).toHaveCount(0);
    await expect(page.getByText("불러오는 중...")).toHaveCount(0, { timeout: 20_000 }); // 무한 로딩 없음
  }
  // 상세 화면: 뉴스 상세·이슈·후보·시연 가이드 링크
  await page.goto("/guide");
  for (const id of ["guide-a", "guide-b", "guide-c"]) await expect(page.getByTestId(id)).toBeVisible();
  const first = page.getByTestId("guide-a").getByRole("link").first();
  await first.click();
  await expect(page.locator("h1").first()).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("3-7 7 — 공개 /preview/: 대시보드 현황·9대 분야 탐색·원문 새 탭 링크·후보 점수 근거·시연 가이드·빈 분야(읽기 전용, 실시간 AI 표시 없음)", async ({ page }) => {
  await page.goto(`${PREVIEW}#/`);
  await expect(page.getByTestId("collection-status")).toContainText("수집·분류 현황");
  await expect(page.getByTestId("collection-status")).toContainText("실시간 수집 결과가 아닙니다");
  await expect(page.locator("#banner")).toContainText("정적 스냅샷");
  const total = Number(await page.getByTestId("total-docs").textContent());
  expect(total).toBeGreaterThan(100);
  const tiles = page.locator('[data-testid^="field-tile-"]');
  await expect(tiles).toHaveCount(9);
  // 분야 타일 → 목록, 건수 = 카드 수(25 한도), 원문 링크 속성
  await page.getByTestId("field-tile-sec").click();
  await expect(page).toHaveURL(/#\/news\?field=sec/);
  const cnt = Number(/(\d+)/.exec((await page.getByTestId("result-count").textContent()) ?? "")![1]);
  await expect(page.getByTestId("news-card")).toHaveCount(Math.min(cnt, 25));
  const a = page.getByTestId("origin-link").first();
  await expect(a).toHaveAttribute("target", "_blank");
  await expect(a).toHaveAttribute("rel", /noopener/);
  expect(await a.getAttribute("href")).toMatch(/^https?:\/\/.+\/.+/);
  // 상세 → 뒤로가기 후 조건 유지
  await page.getByRole("link", { name: /상세 보기/ }).first().click();
  await expect(page.locator("h1")).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/field=sec/);
  // 빈 분야
  await page.goto(`${PREVIEW}#/news?field=conv`);
  await expect(page.getByTestId("empty-state")).toContainText("다른 분야 자료로 채우지 않았습니다");
  // 후보주제 상세: 점수 산정 근거·논쟁 가능성·IITP 선정 아님
  await page.goto(`${PREVIEW}#/candidates`);
  await page.locator("tbody a").first().click();
  await expect(page.getByTestId("dispute-label")).toBeVisible();
  await expect(page.getByTestId("score-breakdown")).toContainText("평가 기준");
  await expect(page.locator("body")).toContainText("IITP 공식 선정 아님");
  await expect(page.locator("body")).toContainText("생성형 AI가 아닌");
  // 시연 가이드 + 시범 출력물(모두 시범 표시)
  await page.goto(`${PREVIEW}#/guide`);
  await expect(page.locator("body")).toContainText("시범·내부용·IITP 미확인");
  await page.goto(`${PREVIEW}#/outputs`);
  await expect(page.locator("body")).toContainText("실제 발간물이 아닙니다");
  // 공개 스냅샷 안전성: 이메일·키·AI 결과·모의 표시 없음
  const raw = await (await page.request.get("http://localhost:4173/data/snapshot.json")).text();
  expect(raw).not.toMatch(/[\w.+-]+@[\w-]+\.[\w.]+/);
  expect(raw).not.toMatch(/sk-ant-|sk-proj-|api[_-]?key|ai_results|모의 응답/i);
});
