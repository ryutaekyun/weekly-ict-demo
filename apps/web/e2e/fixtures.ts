import { test as base, expect, type Browser, type BrowserContext } from "@playwright/test";

// 로컬 기본값은 개발 DB와 분리된 E2E 전용 서버(API 8010 / 화면 3100)다. CI는 이미 깨끗한 DB의 8000/3000 서버를 쓴다(E2E_ISOLATED=0).
const ISOLATED = process.env.E2E_ISOLATED !== "0";
export const API = process.env.E2E_API_URL ?? (ISOLATED ? "http://localhost:8010" : "http://localhost:8000");
export const API_PORT = new URL(API).port;
export const WEB = process.env.E2E_WEB_URL ?? (ISOLATED ? "http://localhost:3100" : "http://localhost:3000");

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript((api) => { (window as unknown as { E2E_API: string }).E2E_API = api; }, API);
    await use(page);
  },
});

/** 별도 브라우저 세션(연구원 A·B 등)을 만든다 — 같은 API 주소 주입 포함 */
export async function newCtx(browser: Browser, opts: Parameters<Browser["newContext"]>[0] = {}): Promise<BrowserContext> {
  const ctx = await browser.newContext({ baseURL: WEB, ...opts });
  await ctx.addInitScript((api) => { (window as unknown as { E2E_API: string }).E2E_API = api; }, API);
  return ctx;
}

export const FEED_BASE = "http://localhost:4174";
export const PY = process.env.E2E_PYTHON ?? (process.platform === "win32" ? "..\\api\\.venv\\Scripts\\python.exe" : "python");
/** 작업자(python -m app.worker --once)를 E2E 서버와 같은 DB 로 실행하기 위한 환경변수 */
export function workerEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env, PYTHONUTF8: "1", PYTHONPATH: ".", COLLECTOR_ALLOW_PRIVATE_HOSTS: "1" } as NodeJS.ProcessEnv;
  if (ISOLATED) env.DATABASE_URL = "sqlite:///./e2e.db";
  return env;
}

export { expect };
