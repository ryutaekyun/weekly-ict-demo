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


class CandidateStatus(str, enum.Enum):
    REC = "rec"  # 추천
    REVIEW = "review"  # 검토중
    HOLD = "hold"  # 보류
    FINAL = "final"  # 확정
    REJECTED = "rejected"  # 반려


class SourceType(str, enum.Enum):
    RSS = "rss"
    API = "api"
    HTML = "html"


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
    DRAFT = "draft"
    REVIEW = "review"
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
