"use client";

/**
 * 공식 원문 링크. 제목을 누르면 원문이 새 탭에서 열리고(플랫폼 화면은 그대로), 주소가 없거나 올바르지 않으면 클릭을 막고 사유를 보여준다.
 * 기관 홈페이지·검색 화면으로 보이는 주소는 열 수는 있지만 '주소 확인 필요'를 함께 표시한다.
 */
export default function OriginalLink({ url, state, blocked, note, isPdf, children, testId }: {
  url: string; state: string; blocked: boolean; note: string | null; isPdf?: boolean; children: React.ReactNode; testId?: string;
}) {
  if (blocked) {
    return (
      <span title={note ?? "원문 링크를 열 수 없습니다"} data-testid={testId} data-link-state={state}>
        <span aria-disabled="true" style={{ color: "var(--ink-muted)", cursor: "not-allowed" }}>{children}</span>{" "}
        <span className="pill hold" title={note ?? undefined}>원문 링크 없음</span>
        <span style={{ display: "block", fontSize: 11.5, color: "var(--ink-muted)" }}>{note}</span>
      </span>
    );
  }
  return (
    <span data-testid={testId} data-link-state={state}>
      <a href={url} target="_blank" rel="noopener noreferrer" title={`공식 원문 열기(새 탭): ${url}`}>{children}</a>
      {isPdf && <span className="pill rec" style={{ marginLeft: 6 }}>PDF</span>}
      {state !== "document" && <span className="pill hold" style={{ marginLeft: 6 }} title={note ?? undefined}>주소 확인 필요</span>}
    </span>
  );
}
