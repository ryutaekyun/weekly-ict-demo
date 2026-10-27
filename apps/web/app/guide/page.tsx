"use client";

import Link from "next/link";
import AppShell from "@/components/AppShell";

const box: React.CSSProperties = { marginBottom: 14 };

/** 시연 가이드 — 어떤 화면에서 어떤 버튼을 누르면 되는지 안내만 한다. 기능을 대신 실행하거나 가짜 결과를 만들지 않는다(링크는 실제 화면으로 이동). */
export default function GuidePage() {
  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>시연 가이드</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        이 플랫폼은 <b>유료 AI를 사용하지 않는 시연 버전</b>입니다. 분류·이슈 묶음·후보 추천은 규칙 기반 자동 분석이며 연구원이 검토합니다. 아래 3가지 경로는 실제 수집 자료로 끝까지 따라가 볼 수 있습니다.
      </p>

      <section className="panel" style={box} data-testid="guide-a">
        <h2 style={{ fontSize: 14, margin: "0 0 6px" }}>시나리오 A — 통신·방송·전파 정책동향 (FCC 공식 자료)</h2>
        <ol style={{ fontSize: 13, margin: 0, paddingLeft: 20 }}>
          <li><Link href="/dashboard">통합 대시보드</Link>에서 &lsquo;방송·전파·위성&rsquo; 분야 타일을 누르거나 <Link href="/documents?field_code=bcast">ICT 정보 수집(방송·전파·위성)</Link>으로 이동합니다.</li>
          <li>제목에 &lsquo;Upper C-Band&rsquo;가 있는 FCC 자료의 제목을 누르면 <b>공식 원문이 새 탭</b>으로 열립니다. <Link href="/documents?field_code=bcast&q=Upper%20C-Band">바로 검색하기</Link></li>
          <li>&lsquo;상세 분석&rsquo; → 규칙 기반 분류·활용가치·핵심 내용 → &lsquo;관련 이슈&rsquo; → 이슈의 후보주제를 엽니다.</li>
          <li>후보주제 화면에서 <b>추천 점수·산정 근거·논쟁 가능성·후속 동향</b>을 확인하고 제목·분야·검토의견·상태(선정·보류·추가 조사 필요)를 수정·저장합니다. 새로고침해도 유지됩니다.</li>
        </ol>
      </section>

      <section className="panel" style={box} data-testid="guide-b">
        <h2 style={{ fontSize: 14, margin: "0 0 6px" }}>시나리오 B — 기술·정책 쟁점 탐색 (검색 → 비교 → 후보 등록)</h2>
        <ol style={{ fontSize: 13, margin: 0, paddingLeft: 20 }}>
          <li><Link href="/documents?field_code=ai&sort=published_desc">인공지능·데이터 분야</Link>에서 키워드 검색·기간·정렬 필터를 적용합니다(상세에서 뒤로 가도 조건이 유지됩니다).</li>
          <li>복수 문서가 묶인 <Link href="/issues">핵심 이슈</Link>를 열어 관련 원문·타임라인·후속 변화를 비교합니다. 상반된 주장이 확인되지 않으면 &lsquo;논쟁 없음&rsquo;으로 표시됩니다.</li>
          <li><Link href="/candidates">후보주제</Link>에서 새 후보를 등록하거나 기존 후보에 근거 원문을 추가·제외합니다.</li>
        </ol>
      </section>

      <section className="panel" style={box} data-testid="guide-c">
        <h2 style={{ fontSize: 14, margin: "0 0 6px" }}>시나리오 C — 보고서·요약본·카드뉴스 제작</h2>
        <ol style={{ fontSize: 13, margin: 0, paddingLeft: 20 }}>
          <li><Link href="/manuscripts">연구·집필 작업실</Link>에서 &lsquo;시범 작성 원고&rsquo;를 엽니다. 왼쪽 <b>원문·근거 작업대</b>에서 원문 확인, 제목·기관·발표일 인용, 발췌문 선택 삽입을 하고 오른쪽 <b>작성 점검</b>으로 날짜·수치·중복을 확인합니다(원문 선택이 곧 검증은 아닙니다).</li>
          <li><Link href="/reports">보고서·요약본 제작</Link>에서 일반호를 구성하고 요약본을 만든 뒤 DOCX·PDF를 내려받습니다.</li>
          <li><Link href="/card-news">카드뉴스 제작</Link>에서 보고서 문장으로 카드를 만들고 PPTX·PNG를 내려받습니다. 모든 출력물은 <b>시범·내부용·IITP 미확인</b> 표시가 붙습니다.</li>
        </ol>
      </section>

      <p style={{ fontSize: 12, color: "var(--ink-muted)" }}>GitHub Pages 공개 시연은 읽기 전용입니다(로그인·저장·파일 생성 없음). 로컬 실행 방법은 저장소의 docs/DEMO_GUIDE.md를 참고하세요.</p>
    </AppShell>
  );
}
