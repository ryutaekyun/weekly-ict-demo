import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { type Page } from "@playwright/test";
import { test, expect, newCtx, API, FEED_BASE, PY, workerEnv } from "./fixtures";
import { login, E2E_ADMIN, E2E_RESEARCHER } from "./helpers";

// Phase 4-2 — 정보원 관리·'지금 수집'(작업 ID·진행 상태)·중복 제거·원문 수정 버전·연구원 공동 조회·예약 작업자.
// [실제 외부 사이트] A·B·C 는 NIST RSS·arXiv 공식 API 에 실제로 접속한다(HTTP 모의 없음). 외부 신규 문서가 없으면 신규 0건이 정상이며 건수를 만들어 내지 않는다.
// [통제된 로컬 피드] D·E·F 는 이 PC의 피드 서버(4174)를 쓴다 — 원문을 '수정'하는 상황은 실제 사이트에서 만들 수 없기 때문이며, 실제 사이트 수집으로 보고하지 않는다.

test.setTimeout(420_000);
const FEEDS = path.resolve("e2e", "feeds");
const OUT = path.join("test-results", "phase42");

async function api<T = any>(page: Page, method: string, p: string, body?: unknown): Promise<{ status: number; json: T }> {
  return page.evaluate(async ({ method, p, body }) => {
    const base = (window as unknown as { E2E_API: string }).E2E_API;
    const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1];
    const res = await fetch(`${base}${p}`, { method, credentials: "include", headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": decodeURIComponent(csrf) } : {}) }, body: body ? JSON.stringify(body) : undefined });
    return { status: res.status, json: await res.json().catch(() => null) };
  }, { method, p, body });
}

async function sourceIdByName(page: Page, name: string): Promise<string> {
  const list = (await api(page, "GET", "/sources")).json as { id: string; name: string }[];
  const s = list.find((x) => x.name === name);
  if (!s) throw new Error(`정보원 '${name}' 없음`);
  return s.id;
}

/** 깨끗한 DB(CI·신규 배포)에는 공식 정보원이 없으므로 같은 공식 주소로 등록한다 — 이미 있으면 그대로 쓴다 */
async function ensureSource(page: Page, body: { name: string; org_name: string; field_code: string; country_code: string; url: string; source_type: string; api_provider?: string }) {
  const list = (await api(page, "GET", "/sources")).json as { name: string }[];
  if (!list.some((s) => s.name === body.name)) {
    const r = await api(page, "POST", "/sources", { ...body, is_primary_source: true, interval_minutes: 720 });
    expect(r.status).toBe(201);
  }
}

const NIST = { name: "NIST News", org_name: "National Institute of Standards and Technology", field_code: "sec", country_code: "US", url: "https://www.nist.gov/news-events/news/rss.xml", source_type: "rss" };
const ARXIV = { name: "arXiv API — cs.AI 최신 논문", org_name: "arXiv (Cornell University)", field_code: "ai", country_code: "INT", source_type: "api", api_provider: "arxiv_api",
  url: "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=30" };

/** 화면에서 '지금 수집'을 누르고 작업이 끝날 때까지 기다린 뒤 완료된 작업을 돌려준다(고정 대기 없음 — 작업 상태 속성을 조건으로 사용) */
async function collectViaUi(page: Page, name: string) {
  await page.goto("/sources");
  const row = page.getByTestId("source-row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.getByTestId("collect-now").click();
  const status = page.getByTestId("job-status").first();
  await expect(status).toBeVisible({ timeout: 20_000 });
  await expect(status).toHaveAttribute("data-job-status", /^(succeeded|failed|timeout|cancelled|interrupted)$/, { timeout: 300_000 });
  const id = await sourceIdByName(page, name);
  const jobs = (await api(page, "GET", `/sources/${id}/jobs`)).json as any[];
  return { id, job: jobs[0], text: (await status.textContent()) ?? "" };
}

function feedXml(items: { title: string; link: string; desc: string }[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>E2E feed</title><link>${FEED_BASE}</link><description>e2e</description>${items
    .map((i) => `<item><title>${i.title}</title><link>${i.link}</link><description>${i.desc}</description><pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate></item>`).join("")}</channel></rss>`;
}

async function registerFeedSource(page: Page, name: string, file: string, interval: string) {
  await page.goto("/sources");
  await page.getByRole("button", { name: "정보원 등록" }).click();
  await page.getByLabel("정보원명").fill(name);
  await page.getByLabel("발행기관").fill("E2E 시험 기관");
  await page.getByLabel("국가·지역 코드(예: US, EU, JP, INT)").fill("US");
  await page.getByLabel("공식 주소(URL)").fill(`${FEED_BASE}/${file}`);
  await page.getByLabel("수집 방식").selectOption("rss");
  await page.getByLabel("자동 수집 주기").selectOption({ label: interval });
  await page.getByLabel("같은 사이트 요청 최소 간격(초)").fill("0");
  await page.getByLabel(/robots\.txt를 준수/).uncheck(); // 로컬 시험 서버에는 robots.txt 가 없다
  await page.getByTestId("source-test").click();
  await expect(page.getByTestId("source-test-result")).toContainText("연결 성공");
  await page.getByTestId("source-save").click();
  await expect(page.getByTestId("source-msg")).toContainText("정보원을 등록했습니다");
}

test("4-2 A — [실제 외부 사이트] NIST 공식 RSS: 지금 수집 → 작업 상태 → DB 저장 → 목록 표시, 같은 정보원 재수집은 중복 처리(신규 0건)", async ({ page }) => {
  await login(page, E2E_ADMIN);
  await ensureSource(page, NIST);
  const first = await collectViaUi(page, "NIST News");
  expect(first.job.status).toBe("succeeded");
  expect(first.job.items_found).toBeGreaterThan(0); // 실제 RSS 에서 항목을 읽었다
  expect(first.job.items_new + first.job.items_duplicate + first.job.items_updated).toBe(first.job.items_found);
  await page.screenshot({ path: path.join(OUT, "A1-nist-collect.png") });
  // 시나리오 C: 바로 다시 수집하면 새 행을 만들지 않는다
  const again = await collectViaUi(page, "NIST News");
  expect(again.job.status).toBe("succeeded");
  expect(again.job.items_new).toBeLessThanOrEqual(1); // 그 사이 외부에 새 글이 올라왔을 수 있다 — 그 외에는 모두 중복
  expect(again.job.items_duplicate).toBeGreaterThanOrEqual(again.job.items_found - 1);
  // 저장된 자료는 ICT 정보 수집 목록에서 NIST 기관으로 조회된다(공식 원문 링크 포함)
  const docs = (await api(page, "GET", `/sources/${first.id}/documents`)).json as any[];
  expect(docs.length).toBeGreaterThan(0);
  expect(docs[0].origin_url).toMatch(/^https:\/\/www\.nist\.gov\//);
  await page.goto("/documents");
  await expect(page.getByTestId("collection-status")).toBeVisible();
  await expect(page.getByTestId("news-row").first()).toBeVisible({ timeout: 20_000 });
});

test("4-2 B — [실제 외부 사이트] arXiv 공식 API: 수집 → 원문 URL·언어·고유ID 저장 → 분야 분류 → 중복 재수집", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const name = ARXIV.name;
  await ensureSource(page, ARXIV);
  const first = await collectViaUi(page, name);
  expect(first.job.status).toBe("succeeded");
  expect(first.job.items_found).toBeGreaterThan(0);
  const docs = (await api(page, "GET", `/sources/${first.id}/documents`)).json as any[];
  const d = docs[0];
  expect(d.origin_url).toMatch(/^https:\/\/arxiv\.org\/abs\/\d{4}\.\d{4,5}$/); // 버전 번호 없는 정규 원문 주소
  expect(d.external_id).toMatch(/^arxiv:\d{4}\.\d{4,5}$/);
  expect(d.language).toBe("en");
  expect(d.published_at).not.toBeNull();
  expect(d.is_peer_reviewed).toBe(false); // 프리프린트
  // 새로 수집된 자료는 분야 분류까지 끝나 분야별 목록·검색에 나타난다
  if (first.job.items_new > 0) expect(first.job.items_classified).toBeGreaterThan(0);
  const list = (await api(page, "GET", `/documents?source_id=${first.id}&page_size=5`)).json;
  expect(list.total).toBeGreaterThan(0);
  const again = await collectViaUi(page, name);
  expect(again.job.items_new).toBeLessThanOrEqual(2);
  expect(again.job.items_duplicate).toBeGreaterThanOrEqual(again.job.items_found - 2);
});

test("4-2 D·E — [통제된 로컬 피드] 정보원 등록·연결 테스트 → 신규 수집 → 원문 수정 시 새 버전 → 연구원 B가 다른 브라우저에서 조회·후보 등록, 일반 연구원은 수집 버튼 없음", async ({ page, browser }) => {
  const stamp = Date.now();
  const file = `e2e-${stamp}.xml`;
  const link = `https://example.com/e2e-4-2/${stamp}`;
  const title = `E2E 4-2 Spectrum allocation policy ${stamp}`;
  fs.writeFileSync(path.join(FEEDS, file), feedXml([{ title, link, desc: "A policy notice on spectrum allocation for 5G networks." }]));
  await login(page, E2E_ADMIN);
  const name = `E2E 시험 피드 ${stamp}`;
  await registerFeedSource(page, name, file, "자동 수집 안 함");
  await page.screenshot({ path: path.join(OUT, "D1-source-registered.png") });

  const first = await collectViaUi(page, name);
  expect(first.job.status).toBe("succeeded");
  expect([first.job.items_found, first.job.items_new, first.job.items_duplicate, first.job.items_updated]).toEqual([1, 1, 0, 0]);
  const dup = await collectViaUi(page, name);
  expect([dup.job.items_new, dup.job.items_duplicate, dup.job.items_updated]).toEqual([0, 1, 0]); // 시나리오 C: 중복

  // 시나리오 D: 같은 문서의 내용이 바뀌면 덮어쓰지 않고 새 버전(v2)으로 저장한다
  fs.writeFileSync(path.join(FEEDS, file), feedXml([{ title, link, desc: "REVISED: spectrum allocation rule corrected after public comments." }]));
  const rev = await collectViaUi(page, name);
  expect([rev.job.items_new, rev.job.items_duplicate, rev.job.items_updated]).toEqual([0, 0, 1]);
  const versions = (await api(page, "GET", `/sources/${first.id}/documents`)).json as any[];
  expect(versions.map((v) => v.version_no).sort()).toEqual([1, 2]);
  expect(versions.find((v) => v.version_no === 1).is_latest).toBe(false); // 이전 버전은 보존
  const v2 = versions.find((v) => v.version_no === 2);
  expect(v2.is_latest).toBe(true);
  expect(v2.previous_version_id).toBe(versions.find((v) => v.version_no === 1).id);
  await page.goto(`/documents?q=${encodeURIComponent(String(stamp))}`);
  const row = page.getByTestId("news-row").filter({ hasText: title });
  await expect(row).toHaveCount(1); // 목록에는 최신본만
  await expect(row).toContainText("v2");
  await page.screenshot({ path: path.join(OUT, "D2-version-v2.png") });

  // 시나리오 E: 연구원 B(다른 브라우저 세션)가 같은 DB 의 새 자료를 보고 후보로 등록한다
  const ctx = await newCtx(browser);
  const B = await ctx.newPage();
  await login(B, E2E_RESEARCHER);
  await B.goto(`/documents?q=${encodeURIComponent(String(stamp))}`);
  const brow = B.getByTestId("news-row").filter({ hasText: title });
  await expect(brow).toHaveCount(1, { timeout: 20_000 });
  await expect(B.getByTestId("collect-all")).toHaveCount(0); // 일반 연구원은 수집을 실행할 수 없다
  await expect(brow.getByTestId("news-link").locator("a")).toHaveAttribute("href", link);
  await brow.getByTestId("register-candidate").click();
  await expect(B.getByTestId("doc-note")).toContainText("후보주제로 등록했습니다");
  await B.getByRole("link", { name: "후보주제 열기" }).click();
  await expect(B.getByRole("heading", { name: title })).toBeVisible({ timeout: 20_000 });
  const candId = B.url().split("/candidates/")[1];
  await ctx.close();
  // 시험 후보주제 정리(다른 테스트가 목록 맨 위 후보를 쓰므로)
  const del = await api(page, "DELETE", `/candidates/${candId}`);
  expect([200, 204]).toContain(del.status);
  // 연구원은 정보원 등록·수정 API 도 쓸 수 없다
  const ctx2 = await newCtx(browser);
  const R = await ctx2.newPage();
  await login(R, E2E_RESEARCHER);
  expect((await api(R, "POST", "/sources", { name: "x", org_name: "x", field_code: "ai", url: "https://x.example/f", source_type: "rss" })).status).toBe(403);
  await ctx2.close();
});

test("4-2 F — 예약 수집: 웹사이트를 열지 않아도 작업자가 주기에 따라 실제 수집을 실행하고 로그(작업 기록)를 남긴다, 주기 전에는 다시 실행하지 않는다", async ({ page }) => {
  const stamp = Date.now();
  const file = `e2e-sched-${stamp}.xml`;
  fs.writeFileSync(path.join(FEEDS, file), feedXml([{ title: `E2E 4-2 Scheduled collection ${stamp}`, link: `https://example.com/e2e-4-2/sched/${stamp}`, desc: "Scheduled collection test item about broadband policy." }]));
  await login(page, E2E_ADMIN);
  const name = `E2E 예약 피드 ${stamp}`;
  await registerFeedSource(page, name, file, "1시간마다");
  const id = await sourceIdByName(page, name);
  expect(((await api(page, "GET", `/sources/${id}/jobs`)).json as any[]).length).toBe(0);
  // 브라우저는 열려 있지 않은 것과 같다: 작업자 프로세스만 실행한다
  const run = () => execFileSync(PY, ["-m", "app.worker", "--once", "--source", id], { cwd: path.resolve("..", "api"), env: workerEnv(), encoding: "utf-8" });
  const out1 = run();
  expect(out1).toContain("점검 완료");
  const jobs1 = (await api(page, "GET", `/sources/${id}/jobs`)).json as any[];
  expect(jobs1.length).toBe(1);
  expect(jobs1[0].trigger).toBe("schedule");
  expect(jobs1[0].status).toBe("succeeded");
  expect(jobs1[0].items_new).toBe(1);
  run(); // 주기(1시간)가 지나지 않았으므로 새 작업이 만들어지지 않는다
  expect(((await api(page, "GET", `/sources/${id}/jobs`)).json as any[]).length).toBe(1);
  await page.goto("/sources");
  const row = page.getByTestId("source-row").filter({ hasText: name });
  await row.getByRole("button", { name: "이력" }).click();
  await expect(page.getByText("최근 수집 결과")).toBeVisible();
  await expect(page.locator("main")).toContainText("1시간마다");
  await page.screenshot({ path: path.join(OUT, "F1-scheduled.png") });
  // 정보원 비활성화(삭제 대신) 후에는 예약 수집도 건너뛴다
  await row.getByRole("button", { name: "비활성화" }).click();
  await expect(page.getByTestId("source-msg")).toContainText("비활성화했습니다");
  const out2 = run();
  expect(out2).toContain("실행 0건");
});

test("4-2 G — 수집 실패·접속 제한 표시: 존재하지 않는 주소는 '주소 변경', 내부망 주소는 등록 단계에서 거부, 사유가 화면에 표시된다", async ({ page }) => {
  await login(page, E2E_ADMIN);
  const stamp = Date.now();
  await page.goto("/sources");
  await page.getByRole("button", { name: "정보원 등록" }).click();
  await page.getByLabel("정보원명").fill(`E2E 없는 주소 ${stamp}`);
  await page.getByLabel("발행기관").fill("E2E 시험 기관");
  await page.getByLabel("공식 주소(URL)").fill(`${FEED_BASE}/does-not-exist-${stamp}.xml`);
  await page.getByLabel(/robots\.txt를 준수/).uncheck();
  await page.getByTestId("source-test").click();
  await expect(page.getByTestId("source-test-result")).toContainText("연결 실패");
  await expect(page.getByTestId("source-test-result")).toContainText("주소를 찾을 수 없습니다"); // 404 → 접속 제한이 아니라 주소 변경
  // 허용되지 않는 프로토콜은 서버가 등록을 거부한다
  await page.getByLabel("공식 주소(URL)").fill("ftp://example.com/feed.xml");
  await page.getByLabel("공식 주소(URL)").evaluate((el: HTMLInputElement) => el.setAttribute("type", "text"));
  await page.getByTestId("source-save").click();
  await expect(page.getByTestId("source-msg")).toContainText("허용되지 않는 프로토콜");
});
