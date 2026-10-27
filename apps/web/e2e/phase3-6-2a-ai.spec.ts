import { test, expect, type Page } from "@playwright/test";
import { login, E2E_ADMIN } from "./helpers";

// Phase 3-6.2A — 첫 실제 호출 안전장치 화면(관리자 1건 승인·예산 상한)과 품질 평가. 서버는 모의 공급자이며 실제 유료 AI 호출은 하지 않는다.
// 승인 필요 상황은 /ai/estimate 응답을 가로채 화면 동작만 검증하고, 서버의 승인·예산 차단 로직은 pytest(test_ai_phase362.py)가 검증한다.

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

async function pickUsableDoc(page: Page): Promise<string> {
  const r = await api(page, "GET", "/documents?has_full_text=true&page_size=30&sort=published_desc");
  for (const d of r.json.items.filter((x: any) => x.extraction_status === "success")) {
    const est = await api(page, "POST", "/ai/estimate", { kind: "document", target_id: d.id });
    if (est.status === 200 && est.json.documents.length > 0) return d.id;
  }
  throw new Error("분석 가능한 문서를 찾지 못함");
}

test("3-6.2A — 실제 AI 호출은 관리자의 1건 승인이 있어야 실행 버튼이 켜지고, 승인 후 예산 상한·1회용 안내가 표시된다(화면 동작)", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const docId = await pickUsableDoc(page);
  let approved = false;
  let approvalBody: any = null;
  const approval = () => ({ id: "ap1", kind: "document", target_id: docId, model: "claude-sonnet-5-5", max_cost_usd: approvalBody?.max_cost_usd ?? 0.1, note: null, expires_at: new Date(Date.now() + 3600_000).toISOString(), used_at: null, used_analysis_id: null, revoked: false });
  await page.route((u) => u.port === "8000" && u.pathname === "/ai/estimate", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, approval_required: true, approval: approved ? approval() : null, est_cost_usd: 0.0607, price_known: true, pricing_version: "anthropic/claude-sonnet-5-5 v1 기준일 2026-10-27" } });
  });
  await page.route((u) => u.port === "8000" && u.pathname === "/ai/approvals", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    approvalBody = JSON.parse(route.request().postData() ?? "{}");
    approved = true;
    await route.fulfill({ json: approval() });
  });
  await page.goto(`/documents/${docId}`);
  const panel = page.getByTestId("ai-panel-document");
  const again = panel.getByRole("button", { name: "다시 분석" });
  if ((await again.count()) > 0) await again.click(); else await panel.getByTestId("ai-run").click();
  await expect(panel.getByTestId("ai-approval-needed")).toContainText("관리자의 1건 승인이 필요합니다");
  await expect(panel.getByTestId("ai-confirm")).toBeDisabled(); // 승인 전에는 실행할 수 없다
  await panel.getByTestId("ai-preflight").click(); // 관리자 사전 점검: 유료 호출 없이 전달 형식·토큰(키가 없으면 미측정)·최대 비용을 보여 준다
  const pre = panel.getByTestId("ai-preflight-result");
  await expect(pre).toContainText("model, max_tokens, system, messages");
  await expect(pre).toContainText("temperature, top_p, top_k, thinking");
  await expect(pre).toContainText("미측정");
  await panel.getByLabel("예산 상한(USD)").fill("0.10");
  await panel.getByTestId("ai-approve").click();
  await expect.poll(() => approvalBody).not.toBeNull();
  expect(approvalBody.kind).toBe("document");
  expect(approvalBody.max_cost_usd).toBe(0.1);
  await expect(panel.getByTestId("ai-approved")).toContainText("예산 상한 $0.1");
  await expect(panel.getByTestId("ai-approved")).toContainText("1회용");
  await expect(panel.getByTestId("ai-confirm")).toBeEnabled();
});

test("3-6.2A — 분석 결과의 품질 평가(7개 항목)는 모든 항목 선택 후에만 저장되고, 모의 응답 평가는 실제 AI 집계와 분리된다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const docId = await pickUsableDoc(page);
  await page.goto(`/documents/${docId}`);
  const panel = page.getByTestId("ai-panel-document");
  const again = panel.getByRole("button", { name: "다시 분석" });
  if ((await again.count()) > 0) await again.click(); else await panel.getByTestId("ai-run").click();
  await panel.getByTestId("ai-confirm").click();
  await expect(panel.getByTestId("ai-result")).toBeVisible({ timeout: 60_000 });
  const ev = panel.getByTestId("ai-evaluation");
  await expect(ev).toContainText("모의 응답 평가는 실제 AI 정확도 집계에 합산되지 않습니다");
  await ev.getByRole("button", { name: "품질 평가(7개 항목)" }).click();
  await expect(ev.getByTestId("ai-eval-save")).toBeDisabled();
  const selects = ev.locator("select");
  await expect(selects).toHaveCount(7);
  for (let i = 0; i < 7; i++) await selects.nth(i).selectOption(i === 3 ? "partial" : "ok");
  await ev.getByLabel("잘못된 출처 연결 사례 수").fill("1");
  await ev.getByLabel("평가 메모(오류·과장 사례)").fill("E2E 모의 평가");
  await ev.getByTestId("ai-eval-save").click();
  await expect(panel.getByRole("status").filter({ hasText: "합산되지 않습니다" })).toBeVisible();
  // 설정 화면: 실제 AI와 모의 응답이 따로 집계된다
  await page.goto("/settings");
  const summary = page.getByTestId("ai-eval-summary");
  await expect(summary).toContainText("합산하지 않습니다");
  await expect(summary).toContainText("실제 AI: 평가 0건");
  await expect(summary).toContainText(/모의 응답: 평가 [1-9]\d*건/);
  await expect(page.getByTestId("ai-gate-status")).toContainText("승인 불필요(모의 공급자");
});
