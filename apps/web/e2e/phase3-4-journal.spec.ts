import fs from "node:fs";
import path from "node:path";
import { type Page } from "@playwright/test";
import { test, expect } from "./fixtures";
import { login, logout, E2E_ADMIN, E2E_RESEARCHER, E2E_REVIEWER } from "./helpers";

// Phase 3-4 — 주간기술동향지: 회차 계획 → 전문가 등록·의뢰 → 외부 저자 제출(보안 검사) → 1차 검토 → 저자 수정 → 2차 심의 → 교정 → 확정 발간본
// 모든 인물·원고는 합성 테스트 데이터이며 실제 이메일은 발송되지 않는다.
test.setTimeout(900_000);

const FIX = path.join(__dirname, "fixtures");
const PW = "E2eTest-Fixed-Pw-Journal-004!";

async function loginExternal(page: Page, email: string) {
  await page.goto("/login");
  await page.getByRole("textbox").first().fill(email);
  await page.locator('input[type="password"]').fill(PW);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL("**/portal");
}

async function pickOption(page: Page, label: string, text: string) {
  const sel = page.getByLabel(label, { exact: true });
  const value = await sel.locator("option", { hasText: text }).first().getAttribute("value");
  expect(value, `${label}에 '${text}' 옵션이 있어야 합니다`).toBeTruthy();
  await sel.selectOption(value!);
}

test("시나리오 P — 주간기술동향지: 의뢰→저자 제출→검토→수정→심의→교정→확정 발간본(합성 데이터)", async ({ page }) => {
  const stamp = Date.now();
  const year = 2030 + (stamp % 60);
  const publish = `${year}-09-15`;
  const expertName = `E2E전문가${stamp}`;
  const authorEmail = `e2e-author-${stamp}@example.com`;
  const reviewerEmail = `e2e-extrev-${stamp}@example.com`;
  const reviewerName = `E2E외부검토자${stamp}`;
  const topic = `E2E 합성 기술동향 ${stamp}`;
  const title = `합성 원고 ${stamp}`;

  // ---- A. 회차 계획: 연간 25회 등록(발간일 자동 확정 없음) → 관리자가 발간일 입력 → 마감일 계산 ----
  await login(page, E2E_ADMIN);
  await page.goto("/journal");
  await page.getByLabel("연도", { exact: true }).fill(String(year));
  await page.getByRole("button", { name: `${year}년 연간 25회 계획 등록` }).click();
  await expect(page.getByText(/발간일은 자동으로 정하지 않았습니다/)).toBeVisible();
  await expect(page.getByTestId("planned-count")).toHaveText("25");
  await page.getByRole("link", { name: `${year}년 제1호`, exact: true }).click();
  await page.waitForURL(/\/journal\/issues\/[0-9a-f-]+$/);
  const issueUrl = page.url();
  await expect(page.getByText("발간일 미입력").first()).toBeVisible(); // 발간일을 넣기 전에는 마감일이 없다
  await page.getByLabel("발간 예정일").fill(publish);
  await page.getByLabel("발간 예정일").blur();
  await expect(page.getByText("발간 예정일을 저장하고 마감일을 다시 계산했습니다")).toBeVisible();
  await expect(page.getByText("발간 예정일을 저장하고")).toBeVisible();
  await expect(page.getByText(publish, { exact: false }).first()).toBeVisible();
  await expect(page.getByText("발간일 미입력")).toHaveCount(0);

  // ---- B. 집필진 확보: 가상 전문가 등록(중복 방지·동의 기록) → 포털 계정 → 의뢰서·안내 메일(미발송) ----
  await page.goto("/journal/experts");
  await page.getByLabel("성명", { exact: true }).fill(expertName);
  await page.getByLabel("소속기관", { exact: true }).fill(`가상대학교${stamp}`);
  await page.getByLabel("이메일", { exact: true }).fill(authorEmail);
  await page.getByLabel("분야 AI").check();
  await page.getByRole("button", { name: "전문가 등록" }).click();
  await expect(page.getByText(/전문가를 등록했습니다/)).toBeVisible();
  await page.getByLabel("성명", { exact: true }).fill(expertName);
  await page.getByLabel("소속기관", { exact: true }).fill(`가상대학교${stamp}`);
  await page.getByRole("button", { name: "전문가 등록" }).click();
  await expect(page.locator("main p[role='alert']")).toContainText("이미 등록된 전문가");
  await page.getByRole("button", { name: `${expertName} 동의 기록` }).click();
  await expect(page.getByRole("row", { name: new RegExp(expertName) })).toContainText("동의");

  await pickOption(page, "연결할 전문가", expertName);
  await page.getByLabel("계정 이메일").fill(authorEmail);
  await page.getByLabel("계정 표시 이름").fill(expertName);
  await page.getByLabel("계정 비밀번호").fill(PW);
  await page.getByRole("button", { name: "계정 생성" }).click();
  await expect(page.getByText(/포털 계정을 만들었습니다/)).toBeVisible();
  await page.getByLabel("계정 종류").selectOption("reviewer");
  await page.getByLabel("계정 이메일").fill(reviewerEmail);
  await page.getByLabel("계정 표시 이름").fill(reviewerName);
  await page.getByLabel("계정 비밀번호").fill(PW);
  await page.getByRole("button", { name: "계정 생성" }).click();
  await expect(page.getByText(/포털 계정을 만들었습니다/)).toBeVisible();

  await page.goto(issueUrl);
  await pickOption(page, "의뢰 전문가", expertName);
  await page.getByLabel("집필 주제", { exact: true }).fill(topic);
  await page.getByLabel("집필 마감일").fill(`${year}-08-01`);
  await page.getByRole("button", { name: "의뢰서 작성" }).click();
  await expect(page.getByText(/의뢰서를 작성했습니다/)).toBeVisible();
  await page.getByRole("button", { name: "안내 메일 미리보기" }).click();
  await expect(page.getByLabel("메일 본문")).toContainText(topic);
  await page.getByRole("button", { name: "발송 대기로 표시" }).click();
  await expect(page.getByText(/실제 발송은 이루어지지 않습니다/)).toBeVisible();
  await expect(page.getByText("안내 메일: 발송 대기(미발송)")).toBeVisible();
  await page.getByRole("button", { name: `${topic} 의뢰함으로 기록` }).click();
  await expect(page.getByText("의뢰함(응답 대기)").first()).toBeVisible();

  // ---- C. 외부 저자: 로그인 → 수락 → 보안 검사(매크로 거부) → DOCX 제출 → 내부 API 차단 ----
  await logout(page);
  await loginExternal(page, authorEmail);
  await page.getByRole("link", { name: topic }).click();
  await page.getByRole("button", { name: "집필 수락" }).click();
  await expect(page.getByText(/집필을 수락했습니다/)).toBeVisible();
  await page.getByLabel("원고 제목", { exact: true }).fill(title);
  await page.getByLabel("영문 제목").fill(`Synthetic Manuscript ${stamp}`);
  await page.getByLabel("원고 요약").fill("합성 요약");
  await page.getByLabel("저자·소속").fill(`${expertName}|가상대학교${stamp}`);
  await page.getByLabel("저작권 이용 동의").check();
  await page.getByLabel("원고 파일").setInputFiles(path.join(FIX, "macro-manuscript.docx"));
  await page.getByRole("button", { name: "원고 제출" }).click();
  await expect(page.locator("main p[role='alert']")).toContainText("매크로"); // 매크로가 든 파일은 접수되지 않는다
  await page.getByLabel("원고 파일").setInputFiles(path.join(FIX, "sample-manuscript.docx"));
  await page.getByRole("button", { name: "원고 제출" }).click();
  await page.waitForURL(/\/portal\/manuscripts\/[0-9a-f-]+$/);
  const authorMsUrl = page.url();
  await expect(page.getByTestId("author-status")).toHaveText("접수 완료");
  await expect(page.getByText(/v1 · 최초 제출/)).toBeVisible();
  await page.goto("/journal");
  await expect(page.locator("main p[role='alert']")).toContainText("외부 전문가 계정은 원고 포털만"); // 내부 API는 서버가 차단한다

  // ---- D. 편집자: 형식 확정 → 외부 검토자 배정 ----
  await logout(page);
  await login(page, E2E_RESEARCHER);
  await page.goto(issueUrl);
  await page.getByRole("link", { name: title }).click();
  await page.waitForURL(/\/journal\/manuscripts\/[0-9a-f-]+$/);
  const msUrl = page.url();
  await expect(page.getByText("분량 기준이 설정되지 않았습니다")).toBeVisible(); // 기준 미설정은 숨기지 않는다
  await page.getByRole("button", { name: "형식 이상 없음 확정" }).click();
  await expect(page.getByTestId("ms-status")).toHaveText("내용 검토 대기");
  await pickOption(page, "검토자 선택", reviewerName);
  await page.getByRole("button", { name: "검토자 배정" }).click();
  await expect(page.getByTestId("ms-status")).toHaveText("검토 진행 중");

  // ---- E. 외부 검토자: 이해상충 확인 → 문단 의견 → 검토 완료(추천 의견) ----
  await logout(page);
  await loginExternal(page, reviewerEmail);
  await page.getByRole("link", { name: title }).first().click();
  await page.getByRole("button", { name: "이해상충 없음 확인" }).click();
  await expect(page.getByText(/이해상충 없음/).first()).toBeVisible();
  await page.getByLabel("의견 대상", { exact: true }).selectOption("paragraph");
  await page.getByLabel("의견 대상 문구").fill("첫 번째 합성 문단은 검토 의견의 대상이 됩니다.");
  await page.getByLabel("검토 의견", { exact: true }).fill("주장의 근거를 보강해 주세요.");
  await page.getByRole("button", { name: "의견 저장" }).click();
  await expect(page.getByText("주장의 근거를 보강해 주세요.")).toBeVisible();
  await pickOption(page, "추천 의견", "경미한 수정 후 게재");
  await page.getByLabel("종합 의견").fill("경미한 수정이 필요합니다.");
  await page.getByRole("button", { name: "검토 완료 제출" }).click();
  await expect(page.getByText(/검토를 완료했습니다/).first()).toBeVisible();

  // ---- F. 편집자 수정 요청 → 저자: 의견 확인·답변·수정본 재제출 ----
  await logout(page);
  await login(page, E2E_RESEARCHER);
  await page.goto(msUrl);
  await page.getByRole("button", { name: "저자에게 수정 요청" }).click();
  await expect(page.getByTestId("ms-status")).toHaveText("수정 요청");
  await logout(page);
  await loginExternal(page, authorEmail);
  await page.goto(authorMsUrl);
  await expect(page.getByTestId("author-status")).toHaveText("수정 요청");
  await expect(page.getByText("주장의 근거를 보강해 주세요.")).toBeVisible();
  await expect(page.getByText(reviewerName)).toHaveCount(0); // 저자에게 검토자 이름은 보이지 않는다
  await page.getByLabel(/^답변:/).fill("근거 문장을 보강했습니다.");
  await page.getByRole("button", { name: "답변 저장" }).click();
  await expect(page.getByText("내 답변: 근거 문장을 보강했습니다.")).toBeVisible();
  await page.getByLabel("수정본 파일").setInputFiles(path.join(FIX, "sample-revision.docx"));
  await page.getByLabel("수정 요약").fill("근거 보강, 문단 1개 추가");
  await page.getByRole("button", { name: "수정본 제출" }).click();
  await expect(page.getByTestId("author-status")).toHaveText("수정본 접수");
  await expect(page.getByText(/v1 · 최초 제출/)).toBeVisible(); // 이전 제출본이 그대로 보관된다
  await expect(page.getByText(/v2 · 수정본/)).toBeVisible();

  // ---- G. 편집자: 버전 비교(수정 확정으로 단정하지 않음) → 2차 검토 배정 ----
  await logout(page);
  await login(page, E2E_RESEARCHER);
  await page.goto(msUrl);
  await page.getByRole("button", { name: "버전 비교" }).click();
  const result = page.getByLabel("버전 비교 결과");
  await expect(result).toContainText("v1 → v2");
  await expect(result).toContainText("내용 확인 필요");
  await expect(result).toContainText("해결 처리는 담당자가 확인");
  await pickOption(page, "검토자 선택", reviewerName);
  await page.getByLabel("검토 차수").selectOption("2");
  await page.getByRole("button", { name: "검토자 배정" }).click();
  await expect(page.getByTestId("ms-status")).toHaveText("검토 진행 중");

  await logout(page);
  await loginExternal(page, reviewerEmail);
  await page.getByRole("link", { name: title }).first().click(); // 최신 배정(2차)
  await page.getByRole("button", { name: "이해상충 없음 확인" }).click();
  await expect(page.getByText(/이해상충 없음/).first()).toBeVisible();
  await pickOption(page, "추천 의견", "게재 적합");
  await page.getByLabel("종합 의견").fill("수정 내용을 확인했습니다.");
  await page.getByRole("button", { name: "검토 완료 제출" }).click();
  await expect(page.getByText(/검토를 완료했습니다/).first()).toBeVisible();

  // ---- H. 의견 해결 → 심의 → 편집자는 확정 불가, 승인권자·관리자가 게재 확정 ----
  await logout(page);
  await login(page, E2E_RESEARCHER);
  await page.goto(msUrl);
  const resolveBtn = page.getByRole("button", { name: "해결 처리" });
  for (let i = 0; i < 10; i++) { // 화면이 다시 그려지는 동안 버튼이 잠깐 사라질 수 있어 두 번 확인한다
    await page.waitForTimeout(700);
    if ((await resolveBtn.count()) === 0) { await page.waitForTimeout(700); if ((await resolveBtn.count()) === 0) break; }
    await resolveBtn.first().click();
  }
  await expect(resolveBtn).toHaveCount(0);
  await page.getByRole("button", { name: "검토 완료 → 심의" }).click();
  await expect(page.getByTestId("ms-status")).toHaveText("심의 완료");
  await expect(page.getByText("승인권자·관리자만 확정할 수 있습니다.")).toBeVisible();
  await logout(page);
  await login(page, E2E_ADMIN);
  await page.goto(msUrl);
  await pickOption(page, "심의 결과", "게재 적합");
  await page.getByLabel("심의 의견").fill("게재 확정");
  await page.getByRole("button", { name: "결과 확정" }).click();
  await expect(page.getByTestId("ms-status")).toHaveText("게재 확정");

  // ---- I. 교정 → 최종 교정 확인 → 회차 구성 → 확정 DOCX·PDF ----
  await page.getByLabel("교정본 파일").setInputFiles(path.join(FIX, "sample-proofread.docx"));
  await page.getByRole("button", { name: "교정본 올리기" }).click();
  await expect(page.getByText(/교정본을 올렸습니다/)).toBeVisible();
  await page.getByRole("button", { name: "최종 교정 확인" }).click();
  await expect(page.locator("main p[role='alert']")).toContainText("점검표 미확인 항목"); // 점검표를 다 확인하기 전에는 확정되지 않는다
  for (const l of ["원문 출처", "그림·표 번호", "참고문헌", "약어", "문장 오류"]) await page.getByLabel(`교정 점검 ${l}`).check();
  await page.getByRole("button", { name: "최종 교정 확인" }).click();
  await expect(page.getByText("최종 교정 확인됨")).toBeVisible();

  await page.goto(issueUrl);
  await page.getByLabel(`게재 배치: ${title}`).check();
  await page.getByRole("button", { name: "게재 구성 저장" }).click();
  await expect(page.getByText("게재 구성을 저장했습니다")).toBeVisible();
  await expect(page.getByText(/IITP 공식 확인 전입니다/)).toBeVisible();
  await page.getByRole("button", { name: "확정 DOCX 생성" }).click();
  await expect(page.getByText("확정 DOCX를 생성했습니다")).toBeVisible({ timeout: 240_000 }); // DOCX도 목차 쪽수를 실제 렌더링으로 확인하므로 시간이 걸린다
  const row = page.locator("section", { hasText: "게재 원고 구성·발간본" }).getByText(/DOCX · 확정\(내부\)/).first();
  await expect(row).toBeVisible();
  const [docx] = await Promise.all([
    page.waitForEvent("download"),
    page.locator("section", { hasText: "게재 원고 구성·발간본" }).getByRole("button", { name: "다운로드" }).first().click(),
  ]);
  const bytes = fs.readFileSync((await docx.path())!);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  expect(bytes.length).toBeGreaterThan(5000);
  await page.getByRole("button", { name: "확정 PDF 생성" }).click();
  await expect(page.getByText("확정 PDF를 생성했습니다")).toBeVisible({ timeout: 240_000 });
  await expect(page.getByText(/PDF · 확정\(내부\) · 성공 · \d+쪽/).first()).toBeVisible();

  // ---- J. 내부 확정과 IITP 확인은 별개 → 발간 이력(외부 업로드 없음) → 대시보드 실적은 DB 기준 ----
  await expect(page.getByText("IITP 공식 확인 전").first()).toBeVisible();
  await page.getByRole("button", { name: "발간 이력 기록" }).click();
  await expect(page.getByText("발간 이력을 기록했습니다")).toBeVisible();
  await expect(page.getByText("IITP 공식 확인 전").first()).toBeVisible(); // 발간 기록을 남겨도 IITP 확인 완료로 바뀌지 않는다
  await page.goto("/journal");
  await page.getByLabel("연도", { exact: true }).fill(String(year));
  await expect(page.getByTestId("planned-count")).toHaveText("25");
  await expect(page.getByTestId("published-count")).toHaveText("1");
});

test("시나리오 Q — 권한: 내부 검토자는 편집 화면·설정에 접근할 수 없고, 연구원은 설정·발간일을 바꿀 수 없다", async ({ page }) => {
  await login(page, E2E_REVIEWER);
  await page.goto("/portal");
  await expect(page.getByRole("heading", { name: "원고 검토 포털" })).toBeVisible();
  await expect(page.getByText("배정된 원고가 없습니다.")).toBeVisible(); // 배정되지 않은 원고는 보이지 않는다
  await page.goto("/journal");
  await expect(page.locator("main p[role='alert']")).toContainText("권한이 필요합니다");
  await logout(page);
  await login(page, E2E_RESEARCHER);
  await page.goto("/journal/settings");
  await expect(page.getByRole("heading", { name: /운영 설정/ })).toBeVisible();
  await page.getByLabel("일정 기준").selectOption("business");
  await expect(page.locator("main p[role='alert']")).toContainText("admin 권한이 필요합니다");
});
