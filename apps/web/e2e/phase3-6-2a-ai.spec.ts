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

test("무료 시연 — 유료 AI 승인·사전 점검·연결 진단·단가 설정 UI는 보이지 않고 잠금 안내만 표시된다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const docId = await pickUsableDoc(page);
  await page.route((u) => u.port === "8000" && u.pathname === "/ai/estimate", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, approval_required: true, approval: null } }); // 서버가 승인을 요구하는 것처럼 보여도 UI는 유료 승인 기능을 노출하지 않는다
  });
  await page.goto(`/documents/${docId}`);
  const panel = page.getByTestId("ai-panel-document");
  const again = panel.getByRole("button", { name: "다시 분석" });
  if ((await again.count()) > 0) await again.click(); else await panel.getByTestId("ai-run").click();
  await expect(panel.getByTestId("ai-estimate")).toBeVisible();
  await expect(panel.getByTestId("ai-approval-needed")).toHaveCount(0);
  await expect(panel.getByTestId("ai-approve")).toHaveCount(0);
  await expect(panel.getByTestId("ai-preflight")).toHaveCount(0);
  await expect(panel.getByTestId("ai-mock-banner")).toContainText("모의 응답(테스트용) — 실제 LLM 분석 아님");
  await page.goto("/settings");
  const admin = page.getByTestId("ai-admin-panel");
  await expect(admin.getByTestId("ai-paid-locked")).toContainText("코드 수준으로 비활성화");
  await expect(admin.getByTestId("ai-diagnose")).toHaveCount(0);
  await expect(admin.getByTestId("ai-price-table")).toHaveCount(0);
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
});
