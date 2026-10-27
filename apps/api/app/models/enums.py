import enum


class FieldCode(str, enum.Enum):
    """RFP가 지정한 ICT 9대 분야 — 데모 화면의 분야 탭과 동일한 명칭/순서를 유지한다."""

    SOC = "soc"  # 디지털사회혁신
    NET = "net"  # 통신·네트워크
    BCAST = "bcast"  # 방송·전파·위성
    SW = "sw"  # SW·자율주행
    AI = "ai"  # 인공지능·데이터
    CONTENT = "content"  # 콘텐츠·미디어
    SEC = "sec"  # 보안·블록체인
    SEMI = "semi"  # 반도체·양자
    CONV = "conv"  # ICT 융합기술


class UserRole(str, enum.Enum):
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    ADMIN = "admin"
    AUTHOR = "author"  # 외부 집필 전문가(주간기술동향지 원고 포털 전용)
    EXT_REVIEWER = "ext_reviewer"  # 외부 검토 전문가(배정된 원고 검토 포털 전용)
    SOURCE_ADMIN = "source_admin"  # 정보원 관리자(정보원 등록·수집 관리)


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"  # 가입 후 관리자 승인 대기 — 내부 업무자료 접근 불가
    APPROVED = "approved"
    REJECTED = "rejected"


class CandidateStatus(str, enum.Enum):
    REC = "rec"  # 추천
    REVIEW = "review"  # 검토중
    HOLD = "hold"  # 보류
    FINAL = "final"  # 확정
    REJECTED = "rejected"  # 반려
    RESEARCH = "research"  # 추가 조사 필요


class SourceType(str, enum.Enum):
    RSS = "rss"  # RSS / Atom 피드
    API = "api"  # 공식 REST API (api_provider 로 응답 형식 선택)
    HTML = "html"  # 공개 HTML 목록 페이지의 링크 수집(허용된 곳만)
    PDF = "pdf"  # 공식 PDF 1건(메타데이터·내용 해시만 보존)
    METADATA = "metadata"  # 이용조건상 전문 저장이 불가한 정보원 — 제목·링크·발표일만 저장


class CollectionJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"  # 서버 재시작·작업자 중단으로 끝까지 가지 못함


ACTIVE_JOB_STATUSES = (CollectionJobStatus.QUEUED, CollectionJobStatus.RUNNING)


class CollectionRunStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceDocumentStatus(str, enum.Enum):
    COLLECTED = "collected"
    PARSED = "parsed"
    DUPLICATE = "duplicate"  # 다른 문서와 내용(content_hash)이 동일한 사본
    UPDATED = "updated"  # 동일 origin_url의 원문이 수정되어 새 버전으로 기록됨(previous_version_id 참조)
    FAILED = "failed"


class DocumentType(str, enum.Enum):
    """ICT 기술동향 조사에 필요한 자료 유형 — 공식 발표문과 언론 보도, 프리프린트와 동료심사 완료
    연구를 구분하기 위해 둔다."""

    POLICY = "policy"  # 정부 정책
    LAW = "law"  # 법령·규제·시행지침
    PAPER = "paper"  # 학술논문(동료심사 여부는 is_peer_reviewed로 별도 표기)
    REPORT = "report"  # 연구기관 기술보고서
    STANDARD = "standard"  # 기술표준·표준화 동향
    STATISTICS = "statistics"  # 국제기구 통계·분석자료
    PRESS_RELEASE = "press_release"  # 기관 공식 보도자료
    TECH_ANNOUNCEMENT = "tech_announcement"  # 기업 공식 기술발표
    NEWS = "news"  # 언론 보도(1차 출처 아님 — requires_primary_source_check로 표기)
    OTHER = "other"


class CollectionErrorType(str, enum.Enum):
    """오류 상황을 구분해 기록한다 — "접속은 됐지만 콘텐츠가 없음"과 "접속 자체가 실패"를 섞지 않는다."""

    HTTP_4XX = "http_4xx"
    HTTP_429 = "http_429"
    HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    PARSE_ERROR = "parse_error"
    ROBOTS_DISALLOWED = "robots_disallowed"
    BLOCKED_URL = "blocked_url"  # 내부망·비허용 주소·프로토콜 등 안전 규칙에 막힘
    TOO_LARGE = "too_large"
    NO_RELEVANT_CONTENT = "no_relevant_content"  # 접속은 성공했으나 해당 분야 실제 콘텐츠를 찾지 못함


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    CORRECTED = "corrected"


class PublicationType(str, enum.Enum):
    WEEKLY_REPORT = "weekly_report"
    CARD_NEWS = "card_news"
    BIWEEKLY_BRIEF = "biweekly_brief"
    TECH_TREND = "tech_trend"


class ManuscriptStatus(str, enum.Enum):
    """초안 작성 → 검토 요청 → 교차검토(→ 수정요청 → 재검토) → 내부 최종 확정의 실제 업무 흐름을 반영한다.
    REVIEW는 기존 값과의 호환을 위해 남겨두되 Phase 3-1부터는 REVIEW_REQUESTED를 쓴다."""

    DRAFT = "draft"
    REVIEW = "review"  # 레거시 — 신규 코드는 REVIEW_REQUESTED 사용
    REVIEW_REQUESTED = "review_requested"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    FINAL = "final"


class ApprovableType(str, enum.Enum):
    CANDIDATE = "candidate"
    MANUSCRIPT = "manuscript"
    PUBLICATION = "publication"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    HOLD = "hold"


class PublicationChannel(str, enum.Enum):
    MAIL = "mail"
    ITFIND = "itfind"
    WEB = "web"


# ---------------------------------------------------------------------------
# Phase 2-2 — 문서별 자동분류·원문추출·활용가치판정·AI분석
# ---------------------------------------------------------------------------


class ClassificationMethod(str, enum.Enum):
    """결과를 만든 주체 — 화면·보고서에 'AI 분석'이라고 표시해도 되는지 판단하는 근거가 된다."""

    RULE_BASED = "rule_based"  # 키워드·규칙 기반 — AI 호출 없음, AI 분석으로 표시 금지
    AI = "ai"  # 실제 LLM 호출 결과
    RESEARCHER = "researcher"  # 연구원이 직접 입력/수정


class ClassificationRelevance(str, enum.Enum):
    MATCHED = "matched"  # ICT 9대 분야 중 하나로 판정됨
    LOW_RELEVANCE = "low_relevance"  # 9대 분야와 관련성 낮음
    PENDING_REVIEW = "pending_review"  # 판단 근거 불충분 — 분류 보류


class ExtractionMethod(str, enum.Enum):
    HTML = "html"
    PDF = "pdf"
    NONE = "none"


class ExtractionStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"  # 일부만 추출(예: PDF 일부 페이지 텍스트 레이어 없음)
    SUMMARY_ONLY = "summary_only"  # 전문 접근 불가/비허용 — 기존 요약문만 사용
    FAILED = "failed"  # 시도했으나 실패
    NOT_ATTEMPTED = "not_attempted"  # 저작권·robots 등으로 시도 자체를 하지 않음


class UsageValueRating(str, enum.Enum):
    PRIORITY = "priority"  # 우선 검토
    GENERAL = "general"  # 일반 검토
    LOW_RELEVANCE = "low_relevance"  # 관련성 낮음
    NEEDS_MORE_INFO = "needs_more_info"  # 추가 확인 필요


# ---------------------------------------------------------------------------
# Phase 2-3 — 동일 이슈 통합·후속변화 추적·쟁점분석·후보주제 추천
# ---------------------------------------------------------------------------


class IssueMembershipType(str, enum.Enum):
    PRIMARY = "primary"  # 클러스터의 최초/대표 문서
    DUPLICATE_REPORT = "duplicate_report"  # 동일 사건을 다룬 서로 다른 출처의 보도
    FOLLOW_UP = "follow_up"  # 후속 변화·조치를 다룬 문서


class ClusterReviewStatus(str, enum.Enum):
    CONFIRMED = "confirmed"  # 자동 통합 신뢰도 높음, 또는 연구원이 확인함
    NEEDS_REVIEW = "needs_review"  # 통합 여부 불확실 — 연구원 검토 대기


class TimelineEventType(str, enum.Enum):
    NEW_ISSUE = "new_issue"  # 최초 등장한 신규 이슈
    ADDITIONAL_ANNOUNCEMENT = "additional_announcement"  # 기존 이슈에 대한 추가 발표
    SUBSTANTIVE_CHANGE = "substantive_change"  # 기존 정책·규제·기술 내용의 실질적 변경
    FOLLOW_UP_ACTION = "follow_up_action"  # 후속 조치·시행·평가 결과
    NO_SUBSTANTIVE_CHANGE = "no_substantive_change"  # 중요한 변화 없이 반복된 보도
    INSUFFICIENT_COMPARISON_DATA = "insufficient_comparison_data"  # 비교 근거 부족 — 추측 금지


class DisputeAnalysisStatus(str, enum.Enum):
    NOT_ANALYZED = "not_analyzed"
    NO_DISPUTES_CONFIRMED = "no_disputes_confirmed"  # 확인된 주요 의견 대립 없음
    DISPUTES_FOUND = "disputes_found"


class EvidenceMatchStatus(str, enum.Enum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"  # 근거 불일치 — 검증 완료로 처리하지 않음
    NOT_VERIFIED = "not_verified"


# ---------------------------------------------------------------------------
# Phase 3-1 — 연구·집필 작업실(원고 편집·근거각주·버전관리·공동검토)
# ---------------------------------------------------------------------------


class ManuscriptSectionKind(str, enum.Enum):
    """일반호 기본 원고 유형 — RFP 발간지침(주요 이슈 1~2건·주요국 동향 2건·분야별 단신·
    향후 일정·요약문) 기준. 특집호는 고정 목차를 강제하지 않으므로 CUSTOM을 쓴다."""

    KEY_ISSUE = "key_issue"
    COUNTRY_TREND = "country_trend"
    FIELD_BRIEF = "field_brief"
    UPCOMING_SCHEDULE = "upcoming_schedule"
    SUMMARY = "summary"
    CUSTOM = "custom"  # 특집호 등 자유 목차


class IitpSelectionStatus(str, enum.Enum):
    """내부 확정(Manuscript.status=approved)과 IITP의 외부 공식 선정은 반드시 구분한다 —
    내부 승인을 IITP 공식 승인으로 자동 간주하지 않는다(지시사항)."""

    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    SELECTED = "selected"
    NOT_SELECTED = "not_selected"


class ReviewCommentStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
