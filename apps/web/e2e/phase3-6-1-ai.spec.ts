import { type Page } from "@playwright/test";
import { test, expect, API_PORT } from "./fixtures";
import { login, E2E_ADMIN, E2E_REVIEWER } from "./helpers";

// Phase 3-6.1 — AI 삽입 위치·취소·원문 변경 재검토·오류 표시·단가/연결 진단 화면.
// 서버는 모의 공급자(AI_PROVIDER=mock)이며 실제 유료 AI 호출은 하지 않는다. 원문 변경·공급자 오류 상황은 API 응답을 가로채 화면 동작을 검증하고,
// 실제 백엔드 동작(원문 해시 변경 감지, 오류 분류 등)은 pytest(test_ai_phase361.py)가 검증한다.

async function api<T = any>(page: Page, method: string, path: string, body?: unknown): Promise<{ status: number; json: T }> {
  return page.evaluate(async ({ method, path, body }) => {
    const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1];
    const res = await fetch(`${(window as unknown as { E2E_API: string }).E2E_API}${path}`, {
      method, credentials: "include",
      headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": decodeURIComponent(csrf) } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    return { status: res.status, json: await res.json().catch(() => null) };
  }, { method, path, body });
}

async function findMultiDocIssue(page: Page): Promise<string> {
  const list = await api(page, "GET", "/issues?page_size=200");
  const issues: any[] = Array.isArray(list.json) ? list.json : list.json.items;
  for (const it of issues.filter((i) => (i.document_count ?? 2) >= 2).slice(0, 60)) {
    const est = await api(page, "POST", "/ai/estimate", { kind: "issue", target_id: it.id });
    if (est.status === 200 && est.json.documents.length >= 2) return it.id;
  }
  throw new Error("원문 전문이 있는 복수 문서 이슈를 찾지 못함");
}

async function manuscriptWithHeadings(page: Page) {
  const issueId = await findMultiDocIssue(page);
  const d = await api(page, "GET", `/issues/${issueId}`);
  const cand = await api(page, "POST", "/candidates", { field_code: d.json.field_code ?? "ai", title: `3-6.1 후보 ${Date.now()}`, issue_cluster_id: issueId, source_document_id: d.json.members[0].document_id });
  const ms = await api(page, "POST", "/manuscripts", { manuscript_type: "key_issue", title: "3-6.1 AI 삽입 원고", candidate_id: cand.json.id });
  const body = {
    type: "doc", content: [
      { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "1. 추진 경과" }] },
      { type: "paragraph", content: [{ type: "text", text: "첫 문단임" }] },
      { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "2. 시사점" }] },
      { type: "paragraph", content: [{ type: "text", text: "마지막 문단임" }] },
    ],
  };
  const saved = await api(page, "PATCH", `/manuscripts/${ms.json.id}`, { body_json: JSON.stringify(body), body: "첫 문단임 마지막 문단임", lock_version: ms.json.lock_version });
  expect(saved.status).toBe(200);
  return ms.json.id as string;
}

async function runDraft(page: Page) {
  await page.getByTestId("tab-ai").click();
  const panel = page.getByTestId("ai-panel-draft");
  const again = panel.getByRole("button", { name: "다시 분석" });
  if ((await again.count()) > 0) await again.click();
  else await panel.getByTestId("ai-run").click();
  await panel.getByTestId("ai-confirm").click();
  await expect(panel.getByTestId("ai-result")).toBeVisible({ timeout: 60_000 });
  return panel;
}

test("3-6.1 E·F — AI 문장을 지정 소제목 아래·현재 커서 문단 뒤에 삽입 → AI 표시·삽입 목록·미검증 각주, 삽입 취소", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const mid = await manuscriptWithHeadings(page);
  await page.goto(`/manuscripts/${mid}`);
  const panel = await runDraft(page);
  const facts = panel.locator('[data-evidence-status="found"][data-researcher-status="unverified"]');
  await expect(facts.nth(1)).toBeVisible();

  // 소제목 '2. 시사점' 아래에 첫 번째 사실 문장 삽입
  await facts.nth(0).getByLabel("원고에 삽입할 문장 선택").check();
  await facts.nth(0).getByLabel("삽입 전 문장 수정").fill("소제목 아래에 넣은 AI 제안 문장임");
  await panel.getByTestId("pos-heading").check();
  await panel.getByLabel("삽입할 소제목").selectOption("2. 시사점");
  await panel.getByTestId("ai-insert").click();
  await expect(panel.getByRole("status").filter({ hasText: "소제목 아래에 삽입" })).toBeVisible({ timeout: 20_000 });
  let fresh = await api(page, "GET", `/manuscripts/${mid}`);
  let texts = JSON.parse(fresh.json.body_json).content.map((n: any) => n.content?.[0]?.text);
  expect(texts).toEqual(["1. 추진 경과", "첫 문단임", "2. 시사점", "소제목 아래에 넣은 AI 제안 문장임", "마지막 문단임"]);
  await expect(page.locator(".ProseMirror .ai-inserted").first()).toContainText("소제목 아래에 넣은 AI 제안 문장임"); // AI 삽입 문장 표시

  // 편집기에서 첫 문단을 클릭해 커서를 둔 뒤 '현재 커서가 있는 문단 뒤'에 삽입
  await page.locator(".ProseMirror p", { hasText: "첫 문단임" }).click();
  const facts2 = panel.locator('[data-evidence-status="found"][data-researcher-status="unverified"]');
  await facts2.nth(1).getByLabel("원고에 삽입할 문장 선택").check();
  await facts2.nth(1).getByLabel("삽입 전 문장 수정").fill("커서 뒤에 넣은 AI 제안 문장임");
  await panel.getByTestId("pos-cursor").check();
  await panel.getByTestId("ai-insert").click();
  await expect(panel.getByRole("status").filter({ hasText: "커서 위치 뒤에 삽입" })).toBeVisible({ timeout: 20_000 });
  fresh = await api(page, "GET", `/manuscripts/${mid}`);
  texts = JSON.parse(fresh.json.body_json).content.map((n: any) => n.content?.[0]?.text);
  expect(texts.slice(0, 3)).toEqual(["1. 추진 경과", "첫 문단임", "커서 뒤에 넣은 AI 제안 문장임"]);
  expect(texts).toContain("마지막 문단임"); // 기존 문장은 그대로

  // 삽입 목록·미검증 각주·삽입 취소
  const list = page.getByTestId("ai-insertions");
  await expect(list.getByTestId("ai-insertion")).toHaveCount(2);
  const fns = await api(page, "GET", `/manuscripts/${mid}/footnotes`);
  expect(fns.json.length).toBeGreaterThanOrEqual(2);
  expect(fns.json.every((f: any) => f.verification_status === "not_verified")).toBe(true);
  await list.getByTestId("ai-insertion").first().getByTestId("ai-insertion-undo").click();
  await expect(list.getByTestId("ai-insertion").first()).toHaveAttribute("data-status", "undone");
  await expect(page.locator(".ProseMirror")).not.toContainText("소제목 아래에 넣은 AI 제안 문장임");
  await expect(page.locator(".ProseMirror")).toContainText("커서 뒤에 넣은 AI 제안 문장임");
  await page.reload();
  await expect(page.locator(".ProseMirror .ai-inserted")).toContainText("커서 뒤에 넣은 AI 제안 문장임"); // 새로고침 후에도 AI 표시 유지
});

test("3-6.1 A·B — 원문 변경 시 삽입된 AI 문장에 '원문 변경·재검토 필요', 변경 전후 표시, 4가지 판단 기록(화면 동작 · 백엔드 감지는 pytest 검증)", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const mid = await manuscriptWithHeadings(page);
  const row = {
    id: "00000000-0000-0000-0000-0000000000aa", analysis_id: "a", claim_id: "c", footnote_mark_id: null, document_id: "d", ai_text: "최종 규정은 2025.2.18.부터 시행됨",
    final_text: "최종 규정은 2025.2.18.부터 시행됨", edited_by_researcher: false, quote_at_insert: "The final rule takes effect on February 18, 2025.", source_hash_at_insert: "h1",
    status: "active", inserted_at: new Date().toISOString(), needs_review: true, history: [],
    change: { current_hash: "h2", baseline_hash: "h1", old_quote: "The final rule takes effect on February 18, 2025.", old_quote_still_in_source: false,
      new_sentence: "The effective date is now March 20, 2025.", similarity: 0.62, removed_facts: ["2025-02-18"], added_facts: ["2025-03-20"], stale_in_sentence: ["2025-02-18"], last_review: null },
  };
  let reviewBody: any = null;
  await page.route((u) => u.port === API_PORT && u.pathname === `/ai/manuscripts/${mid}/insertions`, (route) => route.fulfill({ json: [row] }));
  await page.route((u) => u.port === API_PORT && u.pathname.endsWith("/review") && u.pathname.includes("/ai/insertions/"), async (route) => {
    reviewBody = JSON.parse(route.request().postData() ?? "{}");
    await route.fulfill({ json: { ...row, needs_review: false, change: null, history: [{ resolution: reviewBody.resolution, label: "수정 반영 완료", note: reviewBody.note, reviewer_id: "u", reviewed_at: new Date().toISOString(), reviewed_source_hash: "h2" }] } });
  });
  await page.goto(`/manuscripts/${mid}`);
  await expect(page.getByTestId("tab-ai")).toContainText("재검토");
  await page.getByTestId("tab-ai").click();
  const item = page.getByTestId("ai-insertion").first();
  await expect(item).toHaveAttribute("data-needs-review", "true");
  await expect(item.getByTestId("ai-needs-review")).toHaveText("원문 변경·재검토 필요");
  const detail = item.getByTestId("ai-change-detail");
  await expect(detail).toContainText("The final rule takes effect on February 18, 2025.");   // 삽입 당시 근거
  await expect(detail).toContainText("March 20, 2025");                                      // 현재 원문
  await expect(detail).toContainText("2025-02-18");                                          // 사라진 값
  await expect(detail).toContainText("이전 원문 기준 날짜가 남아 있습니다");
  // 판단 없이 / 사유 없이는 기록되지 않는다
  await item.getByTestId("ai-insertion-review").click();
  await expect(page.getByTestId("ai-insertion-error")).toContainText("판단");
  await detail.getByLabel(/수정 반영 완료/).check();
  await item.getByTestId("ai-insertion-review").click();
  await expect.poll(() => reviewBody).not.toBeNull();
  expect(reviewBody.resolution).toBe("updated");
  expect(reviewBody.note).toBe(""); // 서버가 사유(3자 이상)를 요구한다 — 클라이언트는 빈 값을 그대로 보내 서버 규칙이 적용되게 한다
});

test("3-6.1 H — 공급자 오류는 종류별 정확한 상태·메시지로 표시되고 취소가 비용 없음을 뜻하지 않음을 안내한다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const issueId = await findMultiDocIssue(page);
  await page.goto(`/issues/${issueId}`);
  const cases: [string, string, string][] = [
    ["auth_error", "API 키가 올바르지 않거나 권한이 없습니다(401/403) | anthropic 401", "인증·권한 오류"],
    ["rate_limited", "제공자의 요청 한도를 초과했습니다(429) | anthropic 429", "요청 한도 초과"],
    ["truncated", "응답이 길이 제한으로 잘려 결과를 사용할 수 없습니다 | max_tokens", "응답 잘림"],
  ];
  const panel = page.getByTestId("ai-panel-issue");
  for (const [code, message, title] of cases) {
    await page.route((u) => u.port === API_PORT && u.pathname === "/ai/analyses" , async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({ json: { id: "x", kind: "issue", status: "failed", error_code: code, error_message: message, provider_request_sent: true, verification_status: "ai_unverified", input_documents: [], notes: [], stats: { total: 0, facts: 0, facts_without_valid_evidence: 0, semantic_risk: 0, ratio_without_valid_evidence: 0, researcher_verified: 0 } } });
    });
    const again = panel.getByRole("button", { name: "다시 분석" });
    if ((await again.count()) > 0) await again.click(); else await panel.getByTestId("ai-run").click();
    await panel.getByTestId("ai-confirm").click();
    await expect(panel.getByTestId("ai-state")).toHaveText("분석 실패");
    await expect(panel.getByTestId("ai-error")).toContainText(title);
    await expect(panel.getByTestId("ai-error")).toContainText("비용이 발생했을 수 있습니다");
    await page.unroute((u) => u.port === API_PORT && u.pathname === "/ai/analyses").catch(() => undefined);
  }
});

test("3-6.1 I — 단가 미설정이면 비용을 '계산 불가'로 표시하고(0원 아님), 설정 화면에서 연결 미검증·사용량·단가표를 확인한다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const issueId = await findMultiDocIssue(page);
  await page.route((u) => u.port === API_PORT && u.pathname === "/ai/estimate", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, est_cost_usd: null, price_known: false, pricing_version: null } });
  });
  await page.goto(`/issues/${issueId}`);
  const panel = page.getByTestId("ai-panel-issue");
  const again = panel.getByRole("button", { name: "다시 분석" });
  if ((await again.count()) > 0) await again.click(); else await panel.getByTestId("ai-run").click();
  await expect(panel.getByTestId("ai-cost-unknown")).toContainText("계산 불가");
  await page.unroute((u) => u.port === API_PORT && u.pathname === "/ai/estimate").catch(() => undefined);

  await page.goto("/settings");
  const admin = page.getByTestId("ai-admin-panel");
  await expect(admin.getByTestId("ai-conn-status")).toContainText("모의 공급자");
  await expect(admin.getByTestId("ai-diagnose")).toHaveCount(0); // 무료 시연: 유료 연결 진단 버튼 없음
  await expect(admin.getByTestId("ai-usage")).toContainText("실제 제공자 청구금액이 아닙니다");
  await expect(admin.getByTestId("ai-price-table")).toHaveCount(0);
  // 일반 검토자에게는 연결 진단 버튼이 없다
  await page.context().clearCookies();
  await login(page, E2E_REVIEWER);
  await page.goto("/settings");
  await expect(page.getByTestId("ai-admin-panel")).toBeVisible();
  await expect(page.getByTestId("ai-diagnose")).toHaveCount(0);
});
