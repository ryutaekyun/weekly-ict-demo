import path from "node:path";
import { type Page, type Browser } from "@playwright/test";
import { test, expect, newCtx } from "./fixtures";
import { login, E2E_ADMIN } from "./helpers";

// Phase 4-1 — 회원가입 → 관리자 승인 → 로그인 → 관심 분야, 초대 링크 가입, 연구원 A·B가 서로 다른 브라우저(세션)에서 같은 DB를 함께 사용.
// 모든 단계를 화면 조작으로 진행하며 DB를 직접 고치지 않는다. 가입 계정은 example.com 가상 이메일이다.

test.setTimeout(240_000);
const OUT = path.join("test-results", "phase41");
const PW = "Researcher#2026a";

async function newUser(browser: Browser) {
  const ctx = await newCtx(browser, { viewport: { width: 1366, height: 768 } });
  return { ctx, page: await ctx.newPage() };
}

async function loginAs(page: Page, email: string, password = PW) {
  await page.goto("/login");
  await page.getByRole("textbox").first().fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
}

test("4-1 A — 회원가입 → 승인 대기 로그인 차단 → 관리자 승인 → 로그인 → 관심 분야 저장·유지 → 권한 구분", async ({ browser }) => {
  const stamp = Date.now();
  const a = { email: `e2e-4-1-a-${stamp}@example.com`, name: `연구원A${stamp % 10000}` };
  const A = await newUser(browser);
  const ADM = await newUser(browser);

  // 연구원 A 회원가입(승인 전)
  await A.page.goto("/register");
  await A.page.getByLabel("이름").fill(a.name);
  await A.page.getByLabel("이메일").fill(a.email);
  await A.page.getByLabel("직함(선택)").fill("선임연구원");
  await A.page.locator('input[type="password"]').first().fill(PW);
  await A.page.locator('input[type="password"]').nth(1).fill(PW);
  await A.page.screenshot({ path: path.join(OUT, "01-register.png") });
  await A.page.getByRole("button", { name: "가입 신청" }).click();
  await expect(A.page.getByTestId("register-done")).toContainText("관리자 승인 후 로그인");

  // 승인 전에는 로그인할 수 없다
  await loginAs(A.page, a.email);
  await expect(A.page.locator(".notice.err")).toContainText("승인 대기");
  await expect(A.page).toHaveURL(/\/login/);

  // 관리자가 승인
  await login(ADM.page, E2E_ADMIN);
  await ADM.page.goto("/admin/users");
  const row = ADM.page.getByTestId("pending-row").filter({ hasText: a.email });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await ADM.page.screenshot({ path: path.join(OUT, "02-admin-pending.png") });
  await row.getByRole("button", { name: "승인" }).click();
  await expect(ADM.page.locator(".notice.ok")).toContainText("가입을 승인했습니다");
  await expect(ADM.page.getByTestId("pending-row").filter({ hasText: a.email })).toHaveCount(0);

  // 승인 후 로그인 → 대시보드(업무 화면)
  await loginAs(A.page, a.email);
  await A.page.waitForURL("**/dashboard");
  await expect(A.page.getByTestId("kpi-new")).toBeVisible({ timeout: 20_000 });
  await expect(A.page.getByTestId("recent-docs")).toBeVisible();
  await expect(A.page.getByText("수행체계")).toHaveCount(0); // 제안서 설명이 첫 화면에 없다
  await A.page.screenshot({ path: path.join(OUT, "03-dashboard-a.png") });

  // 관심 분야 저장 → 새로고침 후 유지 → 대시보드에 반영
  await A.page.goto("/account");
  await A.page.getByTestId("fav-ai").check();
  await A.page.getByTestId("fav-sec").check();
  await A.page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(A.page.locator(".notice.ok")).toContainText("저장했습니다");
  await A.page.reload();
  await expect(A.page.getByTestId("fav-ai")).toBeChecked({ timeout: 15_000 });
  await A.page.goto("/dashboard");
  await expect(A.page.getByTestId("favorite-docs")).not.toContainText("관심 ICT 분야를 지정하면", { timeout: 15_000 });

  // 권한 구분: 일반 연구원은 사용자 관리 메뉴·화면·API에 접근할 수 없다
  await expect(A.page.locator('a[href="/admin/users"]')).toHaveCount(0);
  await A.page.goto("/admin/users");
  await expect(A.page.locator(".notice.err")).toContainText("시스템 관리자만");
  const status = await A.page.evaluate(async () => (await fetch((window as unknown as { E2E_API: string }).E2E_API + "/admin/users", { credentials: "include" })).status);
  expect(status).toBe(403);
  await A.ctx.close();
  await ADM.ctx.close();
});

test("4-1 B — 초대 링크 가입(즉시 승인) + 연구원 A·B가 서로 다른 브라우저에서 같은 후보주제를 보고 검토의견을 주고받는다", async ({ browser }) => {
  const stamp = Date.now();
  const A = { email: `e2e-4-1-pa-${stamp}@example.com`, name: `공동A${stamp % 10000}` };
  const B = { email: `e2e-4-1-pb-${stamp}@example.com`, name: `공동B${stamp % 10000}` };
  const ADM = await newUser(browser);
  await login(ADM.page, E2E_ADMIN);

  // 관리자가 두 사람을 초대 → 각자 초대 링크로 가입(승인 대기 없이 바로 로그인)
  const links: string[] = [];
  for (const u of [A, B]) {
    await ADM.page.goto("/admin/users");
    await ADM.page.getByLabel("초대할 이메일").fill(u.email);
    await ADM.page.getByRole("button", { name: "초대 링크 만들기" }).click();
    const box = ADM.page.getByTestId("invite-link");
    await expect(box).toContainText("/register?invite=");
    links.push(((await box.textContent()) ?? "").replace("지금만 표시됩니다: ", "").trim());
  }
  const PA = await newUser(browser);
  const PB = await newUser(browser);
  for (const [ctx, u, link] of [[PA, A, links[0]], [PB, B, links[1]]] as const) {
    await ctx.page.goto(link);
    await ctx.page.getByLabel("이름").fill(u.name);
    await ctx.page.getByLabel("이메일").fill(u.email);
    await ctx.page.locator('input[type="password"]').first().fill(PW);
    await ctx.page.locator('input[type="password"]').nth(1).fill(PW);
    await ctx.page.getByRole("button", { name: "가입 신청" }).click();
    await expect(ctx.page.getByTestId("register-done")).toContainText("바로 로그인");
    await loginAs(ctx.page, u.email);
    await ctx.page.waitForURL("**/dashboard");
  }
  // 같은 초대 링크는 다시 쓸 수 없다
  const again = await newUser(browser);
  await again.page.goto(links[0]);
  await again.page.getByLabel("이름").fill("재사용시도");
  await again.page.getByLabel("이메일").fill(A.email.replace("-pa-", "-pz-"));
  await again.page.locator('input[type="password"]').first().fill(PW);
  await again.page.locator('input[type="password"]').nth(1).fill(PW);
  await again.page.getByRole("button", { name: "가입 신청" }).click();
  await expect(again.page.locator(".notice.err")).toContainText("초대 링크");
  await again.ctx.close();

  // 연구원 A가 후보주제를 등록 → 연구원 B(다른 브라우저 세션)가 같은 DB에서 열람
  const title = `E2E 4-1 공동 후보주제 ${stamp}`;
  await PA.page.goto("/candidates");
  await PA.page.getByRole("button", { name: "후보주제 등록" }).click();
  await PA.page.getByLabel("후보주제 제목").fill(title);
  await PA.page.getByRole("button", { name: "등록", exact: true }).click();
  await expect(PA.page.getByText(`후보주제를 등록했습니다: ${title}`)).toBeVisible();

  await PB.page.goto(`/candidates?q=${encodeURIComponent(title)}`);
  await expect(PB.page.getByRole("link", { name: title })).toBeVisible({ timeout: 15_000 });
  await PB.page.getByRole("link", { name: title }).click();
  await expect(PB.page.getByRole("heading", { name: title })).toBeVisible();
  const comment = `B의 검토의견 ${stamp}`;
  await PB.page.getByPlaceholder("검토 의견을 입력하세요").fill(comment);
  await PB.page.getByRole("button", { name: "등록", exact: true }).last().click();
  await expect(PB.page.getByText(comment)).toBeVisible();
  await PB.page.screenshot({ path: path.join(OUT, "04-b-review.png") });

  // A가 새로고침하면 B의 의견이 보이고, A가 설명을 수정·저장 → B가 새로고침해 확인
  await PA.page.goto(`/candidates?q=${encodeURIComponent(title)}`);
  await PA.page.getByRole("link", { name: title }).click();
  await expect(PA.page.getByText(comment)).toBeVisible({ timeout: 15_000 });
  const desc = `A가 수정한 설명 ${stamp}`;
  await PA.page.getByLabel("후보주제 설명").fill(desc);
  await PA.page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(PA.page.getByText("저장되었습니다")).toBeVisible();
  await PB.page.reload();
  await expect(PB.page.getByLabel("후보주제 설명")).toHaveValue(desc, { timeout: 15_000 });
  await PA.page.screenshot({ path: path.join(OUT, "05-a-edit.png") });

  // 관리자가 A 계정을 비활성화하면 A는 이후 요청이 차단되고 재로그인도 되지 않는다
  await ADM.page.goto("/admin/users");
  const arow = ADM.page.getByTestId("user-row").filter({ hasText: A.email });
  await arow.getByRole("button", { name: "비활성화" }).click();
  await expect(ADM.page.locator(".notice.ok")).toContainText("비활성화했습니다");
  await PA.page.goto("/candidates");
  await expect(PA.page).toHaveURL(/\/login/, { timeout: 15_000 });
  await loginAs(PA.page, A.email);
  await expect(PA.page.locator(".notice.err")).toContainText("비활성화");
  // 시험용 후보주제는 지운다(다른 테스트가 목록 맨 위 후보를 쓰므로 데이터를 남기지 않는다)
  const candId = PB.page.url().split("/candidates/")[1]?.split(/[?#]/)[0];
  if (candId) {
    const st = await ADM.page.evaluate(async (id) => {
      const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1];
      return (await fetch(`${(window as unknown as { E2E_API: string }).E2E_API}/candidates/${id}`, { method: "DELETE", credentials: "include", headers: csrf ? { "x-csrf-token": decodeURIComponent(csrf) } : {} })).status;
    }, candId);
    expect([204, 200]).toContain(st);
  }
  for (const c of [ADM, PA, PB]) await c.ctx.close();
});

test("4-1 C — 주요 화면 콘솔 오류 없음, 1920×1080·1366×768 가로 넘침 없음(로그인·회원가입·대시보드·사용자 관리·내 정보)", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource.*(401|403|404)/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  for (const vp of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
    await page.setViewportSize(vp);
    for (const href of ["/login", "/register"]) {
      await page.goto(href);
      await expect(page.locator("h1")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    }
  }
  await login(page, E2E_ADMIN);
  for (const vp of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
    await page.setViewportSize(vp);
    for (const href of ["/dashboard", "/admin/users", "/account", "/candidates", "/documents"]) {
      await page.goto(href);
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText("불러오는 중...")).toHaveCount(0, { timeout: 20_000 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), `${href} ${vp.width}`).toBeLessThanOrEqual(1);
      if (href === "/dashboard") await page.screenshot({ path: path.join(OUT, `dashboard-${vp.width}.png`) });
    }
  }
  expect(errors, errors.join("\n")).toEqual([]);
});
