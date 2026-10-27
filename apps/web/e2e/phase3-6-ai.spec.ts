import { test, expect, type Page } from "@playwright/test";
import { login, E2E_ADMIN, E2E_REVIEWER } from "./helpers";

// Phase 3-6 — AI 분석 화면 E2E. 서버는 AI_PROVIDER=mock·AI_ALLOW_MOCK=1·AI_MOCK_FLAWS=1 로 띄운 모의 공급자를 쓴다
// (실제 유료 AI 호출 아님 — 화면에 '모의 응답(테스트용)'이 표시되고, 근거 검증은 실제 서버 로직이 수행한다).

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

async function pickDocWithText(page: Page, nth = 0): Promise<{ id: string; title: string }> {
  const r = await api(page, "GET", "/documents?has_full_text=true&page_size=20&sort=published_desc");
  const items = r.json.items.filter((d: any) => d.extraction_status === "success");
  const d = items[nth % items.length]; // CI 픽스처는 문서가 적어 순번을 돌려 쓴다
  return { id: d.id, title: d.title };
}

async function findMultiDocIssue(page: Page): Promise<{ id: string; docs: number }> {
  const list = await api(page, "GET", "/issues?page_size=200");
  const issues: any[] = Array.isArray(list.json) ? list.json : list.json.items;
  for (const it of issues.filter((i) => (i.document_count ?? 2) >= 2).slice(0, 60)) {
    const est = await api(page, "POST", "/ai/estimate", { kind: "issue", target_id: it.id });
    if (est.status === 200 && est.json.documents.length >= 2) return { id: it.id, docs: est.json.documents.length };
  }
  throw new Error("원문 전문이 있는 복수 문서 이슈를 찾지 못함");
}

async function runPanel(page: Page, panelTestId: string, force = false) {
  const panel = page.getByTestId(panelTestId);
  const again = panel.getByRole("button", { name: "다시 분석" });
  await expect(panel.getByTestId("ai-state")).not.toHaveText("분석 중");
  if (force && (await again.count()) > 0) await again.click(); // 이미 결과가 있으면 새로 분석(재사용하지 않음)
  else await panel.getByTestId("ai-run").click();
  await expect(panel.getByTestId("ai-estimate")).toBeVisible();
  await expect(panel.getByTestId("ai-estimate")).toContainText("예상 비용");
  await panel.getByTestId("ai-confirm").click();
  await expect(panel.getByTestId("ai-result")).toBeVisible({ timeout: 60_000 });
  return panel;
}

test("3-6 A·B·H — 공식 원문 선택 → AI 분석 요청 → 결과 저장·새로고침 유지 → 주장의 원문 근거 열람 → 근거 없는 날짜는 검증 실패 표시", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const doc = await pickDocWithText(page, 0);
  await page.goto(`/documents/${doc.id}`);
  const panel = page.getByTestId("ai-panel-document");
  await expect(panel.getByTestId("ai-state")).toContainText(/분석 대기|분석 완료/); // 이전 실행 결과가 남아 있을 수 있다
  await expect(panel.getByText("모의 응답(테스트용)").first()).toBeVisible();
  await runPanel(page, "ai-panel-document", true);
  await expect(panel.getByTestId("ai-state")).toContainText("분석 완료");
  // 분석 성공 ≠ 검증 완료: 검증 실패 시연 문장이 있어 '근거 불일치' 상태이고, 연구원이 확인하기 전에는 검증 완료가 아니다
  await expect(panel.getByTestId("ai-verification")).toContainText(/근거 불일치|연구원 미검증/);
  await expect(panel.getByTestId("ai-verification")).not.toContainText("검증 완료");
  await expect(panel.locator('[data-evidence-status="value_mismatch"]').first()).toContainText("근거 불일치");  // H: 원문에 없는 날짜(2099.1.1.)
  await expect(panel.locator('[data-evidence-status="not_found"]').first()).toContainText("검증 실패");           // H: 원문에 없는 발췌문
  // B: 원문 근거 열람 — 발췌문·위치·공식 원문 링크(새 탭)
  const found = panel.locator('[data-evidence-status="found"]').first();
  await found.getByRole("button", { name: "원문 근거 보기" }).click();
  await expect(found.getByTestId("ai-evidence").first()).toContainText("원문에서 확인됨");
  const orig = found.getByRole("link", { name: /공식 원문/ }).first();
  await expect(orig).toHaveAttribute("target", "_blank");
  await expect(orig).toHaveAttribute("rel", /noopener/);
  // 저장·새로고침 후에도 같은 결과가 보인다
  await page.reload();
  await expect(page.getByTestId("ai-panel-document").getByTestId("ai-result")).toBeVisible({ timeout: 15_000 });
  // 연구원 검증은 별도 동작: 근거가 확인된 문장은 한 번에, 그렇지 않은 문장은 사유가 필요하다
  const p2 = page.getByTestId("ai-panel-document");
  await p2.locator('[data-evidence-status="found"]').first().getByRole("button", { name: "검증 완료" }).click();
  await expect(p2.locator('[data-evidence-status="found"][data-researcher-status="verified"]').first()).toBeVisible();
  await p2.locator('[data-evidence-status="value_mismatch"]').first().getByRole("button", { name: "검증 완료" }).click();
  await expect(p2.getByTestId("ai-error")).toContainText("사유");
});

test("3-6 C — AI 미설정 상태: 가짜 결과 없이 'AI 설정 필요'를 표시하고 규칙 기반 화면은 그대로 동작한다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const doc = await pickDocWithText(page, 1);
  await page.route((u) => u.port === "8000" && u.pathname === "/ai/status", (route) =>
    route.fulfill({ json: { configured: false, provider: null, model: null, is_mock: false, daily_limit_per_user: 30, message: "AI 설정 필요 — 서버 환경변수가 설정되지 않아 AI 분석을 실행할 수 없습니다." } }));
  await page.goto(`/documents/${doc.id}`);
  const panel = page.getByTestId("ai-panel-document");
  await expect(panel.getByTestId("ai-state")).toHaveText("AI 설정 필요");
  await expect(panel.getByTestId("ai-config-needed")).toContainText("규칙 기반 분석 결과는 이 화면에서 그대로");
  await expect(panel.getByTestId("ai-run")).toBeDisabled();
  await expect(page.getByTestId("detail-origin-link")).toBeVisible(); // 기존 기능(원문 링크·분류 화면)은 정상
  await expect(page.locator("h1")).toHaveText(doc.title);
  await page.goto("/documents");
  await expect(page.getByTestId("news-row").first()).toBeVisible();
});

test("3-6 D·E — 복수 문서 이슈 AI 쟁점 분석 → 근거 확인, AI 후보주제 제안 → 연구원 수정 → 후보 등록", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const issue = await findMultiDocIssue(page);
  await page.goto(`/issues/${issue.id}`);
  const ip = await runPanel(page, "ai-panel-issue", true);
  await expect(ip.getByText("⑤ 실제 확인된 정책·기술적 논쟁")).toBeVisible();
  await expect(ip.getByTestId("ai-stats")).toContainText("사실 문장");
  await ip.locator('[data-evidence-status="found"]').first().getByRole("button", { name: "원문 근거 보기" }).click();
  await expect(ip.getByTestId("ai-evidence").first()).toBeVisible();
  await expect(ip.getByText(/사용한 원문 \d+건/)).toBeVisible();
  // 후보주제 제안: 제안 제목을 연구원이 고쳐 등록한다(상태는 AI가 정하지 않음)
  const cp = await runPanel(page, "ai-panel-candidate", true);
  const title = `3-6 E2E 후보 ${Date.now()}`;
  await cp.getByLabel("AI 제안 제목(수정)").fill(title);
  await cp.getByTestId("ai-save-candidate").click();
  await expect(cp.getByRole("status").filter({ hasText: "후보주제를 등록" })).toBeVisible();
  const list = await api(page, "GET", `/candidates?q=${encodeURIComponent(title)}`);
  expect(list.json.length).toBe(1);
  expect(list.json[0].status).toBe("rec"); // 선정·확정이 아닌 일반 신규 후보 상태
});

test("3-6 F·G — AI 초안 미리보기 → 선택한 문장만 원고에 삽입, 연구원이 입력한 기존 원고는 덮어쓰이지 않고 삽입 각주는 미검증", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const issue = await findMultiDocIssue(page);
  const d = await api(page, "GET", `/issues/${issue.id}`);
  const cand = await api(page, "POST", "/candidates", { field_code: d.json.field_code ?? "ai", title: `3-6 원고용 후보 ${Date.now()}`, issue_cluster_id: issue.id, source_document_id: d.json.members[0].document_id });
  expect(cand.status).toBe(201);
  const ms = await api(page, "POST", "/manuscripts", { manuscript_type: "key_issue", title: "3-6 AI 삽입 원고", candidate_id: cand.json.id });
  const own = "연구원이 먼저 쓴 문장임";
  const body = JSON.stringify({ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: own }] }] });
  expect((await api(page, "PATCH", `/manuscripts/${ms.json.id}`, { body_json: body, body: own, lock_version: ms.json.lock_version })).status).toBe(200);

  await page.goto(`/manuscripts/${ms.json.id}`);
  await page.getByTestId("tab-ai").click();
  const panel = await runPanel(page, "ai-panel-draft", true);
  // F: 미리보기에서 사실 문장 하나만 고르고 고쳐서 삽입 — 편집기에는 아직 아무것도 들어가지 않았다
  await expect(page.locator(".ProseMirror")).not.toContainText("[모의]");
  const pick = panel.locator('[data-evidence-status="found"][data-researcher-status="unverified"]').first();
  const claimText = (await pick.locator("div").first().innerText()).split("\n")[0];
  expect(claimText.length).toBeGreaterThan(5);
  await pick.getByLabel("원고에 삽입할 문장 선택").check();
  await pick.getByLabel("삽입 전 문장 수정").fill("연구원이 다듬은 AI 제안 문장임");
  // G: 삽입 직전 편집기에 연구원이 직접 입력 — 저장 대기 중이어도 AI 삽입이 이를 덮어쓰지 않아야 한다
  await page.locator(".ProseMirror").click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type(" 삽입 직전에 입력한 문장임");
  await panel.getByTestId("ai-insert").click();
  await expect(panel.getByRole("status").filter({ hasText: "원고 끝에 삽입" })).toBeVisible({ timeout: 20_000 });
  const editor = page.locator(".ProseMirror");
  await expect(editor).toContainText(own);
  await expect(editor).toContainText("삽입 직전에 입력한 문장임");
  await expect(editor).toContainText("연구원이 다듬은 AI 제안 문장임");
  await expect(editor).not.toContainText("[모의-검증실패");  // 선택하지 않은 문장은 들어가지 않는다
  await page.reload();
  await expect(page.locator(".ProseMirror")).toContainText("연구원이 다듬은 AI 제안 문장임");
  await expect(page.locator(".ProseMirror")).toContainText(own);
  const fns = await api(page, "GET", `/manuscripts/${ms.json.id}/footnotes`);
  expect(fns.json.length).toBeGreaterThanOrEqual(1);
  expect(fns.json.every((f: any) => f.verification_status === "not_verified")).toBe(true); // 자동 검증 완료 아님
});

test("3-6 I·J — 권한: 검토자는 AI 호출 불가, 같은 원문 버전 재요청은 이전 결과를 재사용하며 호출한도·비용 확인 없이는 실행되지 않는다", async ({ page, browser }) => {
  await login(page, E2E_ADMIN);
  const doc = await pickDocWithText(page, 2);
  // 비용 확인 없이 호출하면 서버가 거부한다
  const noConfirm = await api(page, "POST", "/ai/analyses", { kind: "document", target_id: doc.id, force: true });
  expect(noConfirm.status).toBe(428);
  const first = await api(page, "POST", "/ai/analyses", { kind: "document", target_id: doc.id, confirm_cost: true });
  expect(first.status).toBe(200);
  const second = await api(page, "POST", "/ai/analyses", { kind: "document", target_id: doc.id, confirm_cost: true });
  expect(second.json.id).toBe(first.json.id);
  expect(second.json.reused).toBe(true); // J: 중복 요청 → 이전 결과 재사용(호출·비용 없음)
  // 화면에서도 '다시 분석'이 아닌 일반 요청은 재사용 안내를 보여준다
  await page.goto(`/documents/${doc.id}`);
  const panel = await runPanel(page, "ai-panel-document", false);
  await expect(page.getByText("이전 분석 결과를 다시 보여줍니다")).toBeVisible();
  await expect(panel.getByTestId("ai-state")).toContainText("분석 완료");
  // I: 검토자(reviewer) 계정은 AI 분석을 요청할 수 없다
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await login(p2, E2E_REVIEWER);
  const denied = await api(p2, "POST", "/ai/analyses", { kind: "document", target_id: doc.id, confirm_cost: true });
  expect(denied.status).toBe(403);
  await ctx.close();
});
