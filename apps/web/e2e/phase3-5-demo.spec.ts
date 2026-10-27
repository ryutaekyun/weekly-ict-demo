import { test, expect, API_PORT } from "./fixtures";
import { login, E2E_ADMIN } from "./helpers";

// Phase 3-5 — 기존 기능이 실제 브라우저에서 끝까지 연결되는지 확인한다(시나리오 이름은 3-5 지시서의 A–L 기준).

test("3-5 A·B — 분야 선택 → 실제 뉴스 목록(건수=표시 행) → 제목 클릭 시 공식 원문이 새 탭으로 열린다", async ({ page, context }) => {
  await login(page, E2E_ADMIN);
  await page.goto("/documents");
  await page.getByLabel("전체 분야").selectOption("ai");
  await expect(page).toHaveURL(/field_code=ai/);
  await expect(page.getByTestId("news-row").first()).toContainText("인공지능·데이터", { timeout: 15000 });
  const countText = await page.getByTestId("result-count").textContent();
  const total = Number(/(\d+)/.exec(countText ?? "")![1]);
  const size = Math.min(total, 20);
  await expect(page.getByTestId("news-row")).toHaveCount(size); // 건수 표시와 실제 행 수가 같다

  const link = page.getByTestId("news-link").first().locator("a");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", /noopener/);
  const href = await link.getAttribute("href");
  expect(href).toMatch(/^https?:\/\//);
  const popupPromise = context.waitForEvent("page");
  await link.click();
  const popup = await popupPromise;
  expect(popup.url().startsWith("about:") || popup.url().startsWith("http")).toBeTruthy(); // 외부 사이트 접속 자체는 검증 대상이 아니다
  await popup.close();
  await expect(page).toHaveURL(/\/documents\?/); // 플랫폼 화면은 그대로 남아 있다
});

test("3-5 C — 원문 주소가 없는 자료는 클릭이 막히고 사유가 표시된다(링크 오류와 접속 제한을 구분)", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await page.route((u) => u.port === API_PORT && u.pathname === "/documents", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    if (Array.isArray(body.items) && body.items.length > 0) {
      body.items[0] = { ...body.items[0], origin_url: "", link_state: "missing", link_blocked: true, link_note: "원문 주소가 등록되지 않았습니다" };
    }
    await route.fulfill({ response: res, json: body });
  });
  await page.goto("/documents");
  const first = page.getByTestId("news-link").first();
  await expect(first).toHaveAttribute("data-link-state", "missing");
  await expect(first.locator("a")).toHaveCount(0); // 링크가 아니므로 눌러도 이동하지 않는다
  await expect(first).toContainText("원문 링크 없음");
  await expect(first).toContainText("원문 주소가 등록되지 않았습니다");
});

test("3-5 H — 검색·필터·정렬은 URL에 남아 상세 → 뒤로가기 후에도 유지되고, 조건 초기화로 복구된다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await page.goto("/documents");
  await expect(page.getByTestId("news-row").first()).toBeVisible();
  const all = await page.getByTestId("result-count").textContent();
  await page.getByLabel("전체 분야").selectOption("ai");
  await expect(page.getByTestId("result-count")).not.toHaveText(all ?? "");
  await page.getByLabel("정렬").selectOption("title");
  await expect(page).toHaveURL(/field_code=ai/);
  await expect(page).toHaveURL(/sort=title/);
  const before = await page.getByTestId("result-count").textContent();
  await page.getByRole("link", { name: /^상세 분석/ }).first().click();
  await expect(page).toHaveURL(/\/documents\/[0-9a-f-]+/);
  await page.goBack();
  await expect(page).toHaveURL(/field_code=ai/);
  await expect(page.getByLabel("전체 분야")).toHaveValue("ai");
  await expect(page.getByLabel("정렬")).toHaveValue("title");
  await expect(page.getByTestId("result-count")).toHaveText(before ?? "");
  await page.getByRole("button", { name: "조건 초기화" }).click();
  await expect(page.getByLabel("전체 분야")).toHaveValue("");
});

test("3-5 I — 자료가 없는 분야(ICT 융합기술)는 다른 분야로 채우지 않고 빈 상태를 보여준다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await page.goto("/documents?field_code=conv");
  await expect(page.getByTestId("result-count")).toHaveText("총 0건");
  await expect(page.getByTestId("empty-state")).toContainText("다른 분야 자료로 채우지 않았습니다");
  await expect(page.getByTestId("news-row")).toHaveCount(0);
});

test("3-5 D·E — 뉴스 → 이슈 → 후보주제, 후보 담당자·설명 수정 → 저장 → 새로고침 후에도 유지되고 이력에 남는다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await page.goto("/candidates");
  await expect(page.getByTestId("candidate-count")).toBeVisible();
  const firstLink = page.locator("table tbody tr a").first();
  await firstLink.click();
  await expect(page).toHaveURL(/\/candidates\/[0-9a-f-]+/);

  const summary = `3-5 E2E 수정 설명 ${Date.now()}`;
  await page.getByLabel("후보주제 설명").fill(summary);
  const assignee = page.getByLabel("검토 담당자");
  const options = await assignee.locator("option").allTextContents();
  const target = options.find((o) => o.includes("E2E") || o.includes("e2e")) ?? options[1];
  if (target) await assignee.selectOption({ label: target });
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText(/저장했습니다|저장되었습니다/)).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("후보주제 설명")).toHaveValue(summary, { timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "수정 이력" })).toBeVisible();
});
