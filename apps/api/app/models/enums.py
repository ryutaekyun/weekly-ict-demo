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
    DUPLICATE = "duplicate"
    FAILED = "failed"


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
