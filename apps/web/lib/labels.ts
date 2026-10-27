export const FIELD_LABELS: Record<string, string> = {
  soc: "디지털사회혁신",
  net: "통신·네트워크",
  bcast: "방송·전파·위성",
  sw: "SW·자율주행",
  ai: "인공지능·데이터",
  content: "콘텐츠·미디어",
  sec: "보안·블록체인",
  semi: "반도체·양자",
  conv: "ICT 융합기술",
};

export const CANDIDATE_STATUS_LABELS: Record<string, string> = {
  rec: "추천",
  review: "검토중",
  hold: "보류",
  final: "확정",
  rejected: "반려",
  research: "추가 조사 필요",
};

export const RELEVANCE_LABELS: Record<string, string> = {
  matched: "분야 매칭",
  low_relevance: "관련성 낮음",
  pending_review: "분류 보류",
};

export const METHOD_LABELS: Record<string, string> = {
  rule_based: "규칙 기반",
  ai: "AI 분석(미검증 여부는 별도 표시)",
  researcher: "연구원 확인",
};

export const EXTRACTION_STATUS_LABELS: Record<string, string> = {
  success: "전문 확보",
  partial: "부분 추출",
  summary_only: "요약만 확보",
  failed: "추출 실패",
  not_attempted: "시도 안 함",
};

export const VALUE_RATING_LABELS: Record<string, string> = {
  priority: "우선 검토",
  general: "일반 검토",
  low_relevance: "관련성 낮음",
  needs_more_info: "추가 확인 필요",
};

export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  policy: "정부 정책",
  law: "법령·규제",
  paper: "학술논문",
  report: "연구보고서",
  standard: "기술표준",
  statistics: "통계·분석자료",
  press_release: "보도자료",
  tech_announcement: "기업 기술발표",
  news: "언론 보도",
  other: "기타",
};

export const CLUSTER_REVIEW_LABELS: Record<string, string> = {
  confirmed: "통합 확정",
  needs_review: "검토 대기",
};

export const MEMBERSHIP_TYPE_LABELS: Record<string, string> = {
  primary: "최초 문서",
  duplicate_report: "동일 사건 보도",
  follow_up: "후속 변화",
};

export const TIMELINE_EVENT_LABELS: Record<string, string> = {
  new_issue: "신규 이슈",
  additional_announcement: "추가 발표",
  substantive_change: "실질적 변경",
  follow_up_action: "후속 조치",
  no_substantive_change: "변화 없음(반복 보도)",
  insufficient_comparison_data: "비교 자료 부족",
};

export const DISPUTE_STATUS_LABELS: Record<string, string> = {
  not_analyzed: "분석 전",
  no_disputes_confirmed: "확인된 대립 없음",
  disputes_found: "논쟁 발견(연구원 확인 필요)",
};

export const ROLE_LABELS: Record<string, string> = {
  researcher: "연구원",
  reviewer: "검토자",
  approver: "최종승인자",
  admin: "관리자",
  author: "외부 집필 전문가",
  ext_reviewer: "외부 검토 전문가",
};

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

export function fmtDateOnly(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" });
}

export const REPORT_TYPE_LABELS: Record<string, string> = { general: "일반호 보고서", special: "특집호 보고서", summary: "요약본" };
export const REPORT_STATUS_LABELS: Record<string, string> = { draft: "작성 중", final: "출력용 확정" };
