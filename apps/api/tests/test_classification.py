from app.models.enums import ClassificationMethod, ClassificationRelevance, FieldCode, SourceType
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import classification as classification_service
from datetime import datetime, timezone


def _make_source(db_session, field_code=FieldCode.SEC) -> Source:
    source = Source(
        name="Test Source", org_name="Test Org", field_code=field_code, country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_document(db_session, source, title="Title", field_code=None) -> SourceDocument:
    from app.models.enums import DocumentType, SourceDocumentStatus

    doc = SourceDocument(
        source_id=source.id, title=title, origin_url="https://example.org/a",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash="x",
        status=SourceDocumentStatus.COLLECTED, field_code=field_code or source.field_code,
        collection_method=SourceType.RSS, document_type=DocumentType.NEWS,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_rule_based_classification_uses_content_not_source_field(db_session, monkeypatch):
    """Phase 2-1 버그 재현 방지 — 출처가 SEC로 고정돼 있어도 내용이 반도체면 SEMI로 분류돼야 한다."""
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session, field_code=FieldCode.SEC)  # 출처는 보안·블록체인으로 고정
    doc = _make_document(db_session, source, title="New semiconductor chip foundry export control policy")

    text = "This semiconductor chip foundry supply chain export control policy affects quantum computing hardware."
    result = classification_service.run_classification(db_session, doc, text=text, prefer_ai=True)

    assert result.primary_field_code == FieldCode.SEMI
    assert result.primary_field_code != source.field_code
    assert result.method == ClassificationMethod.RULE_BASED  # AI 미설정 환경이므로 규칙 기반이어야 함
    assert result.relevance == ClassificationRelevance.MATCHED


def test_deceleration_g_force_units_do_not_trigger_false_5g_6g_match(db_session, monkeypatch):
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — 차량 안전문서의 '0.5g/0.6g 감속도' 단위가
    통신분야 '5G/6G' 키워드로 오매칭되면 안 된다."""
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session, field_code=FieldCode.SW)
    doc = _make_document(db_session, source, title="Automated Driving System Deceleration Test")

    text = "The vehicle must have a peak deceleration of 0.5g during the test. NHTSA proposed a 0.6g threshold. " * 10
    result = classification_service.run_classification(db_session, doc, text=text, prefer_ai=True)

    assert result.primary_field_code != FieldCode.NET


def test_w3c_technical_standard_is_not_misclassified_as_social_accessibility_policy(db_session, monkeypatch):
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — WCAG 같은 W3C 기술표준 공지가 'accessibility'
    단어 하나만으로 디지털사회혁신(SOC)으로 오분류되면 안 되고 통신·네트워크(NET)로 가야 한다."""
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session, field_code=FieldCode.NET)
    doc = _make_document(db_session, source, title="Authorized Translations of WCAG 2.2 and 2.1 in French updated")

    text = "The World Wide Web Consortium (W3C) has published updated Authorized French Translations of Web Content Accessibility Guidelines (WCAG)."
    result = classification_service.run_classification(db_session, doc, text=text, prefer_ai=True)

    assert result.primary_field_code == FieldCode.NET


def test_low_score_text_is_pending_review_not_forced_into_a_field(db_session, monkeypatch):
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session)
    doc = _make_document(db_session, source, title="Performance Review Board Membership")

    text = "The agency publishes the names of members selected to serve on its Performance Review Board."
    result = classification_service.run_classification(db_session, doc, text=text, prefer_ai=True)

    assert result.primary_field_code is None
    assert result.relevance == ClassificationRelevance.PENDING_REVIEW


def test_classification_without_ai_is_never_labeled_as_ai_method(db_session, monkeypatch):
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session, field_code=FieldCode.AI)
    doc = _make_document(db_session, source)

    result = classification_service.run_classification(db_session, doc, text="artificial intelligence large language model", prefer_ai=True)

    assert result.method == ClassificationMethod.RULE_BASED
    assert "AI 분석이 아니라" in result.reasoning or "규칙 기반" in result.reasoning


def test_researcher_override_is_recorded_with_history(db_session, monkeypatch):
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session, field_code=FieldCode.SEC)
    doc = _make_document(db_session, source)
    classification_service.run_classification(db_session, doc, text="cybersecurity encryption", prefer_ai=True)

    from app.models.enums import UserRole
    from tests.conftest import make_user

    reviewer = make_user(db_session, "reviewer-override@example.com", UserRole.REVIEWER)
    updated = classification_service.override_classification(
        db_session, doc, user_id=reviewer.id, primary_field_code=FieldCode.CONV,
        related_field_codes=[], relevance=ClassificationRelevance.MATCHED, reason="연구원 판단: 융합기술이 더 적절함",
    )

    assert updated.primary_field_code == FieldCode.CONV
    assert updated.method == ClassificationMethod.RESEARCHER
    assert updated.is_researcher_overridden is True

    from app.models.document_classification import DocumentClassificationHistory

    history_rows = (
        db_session.query(DocumentClassificationHistory)
        .filter_by(document_id=doc.id)
        .order_by(DocumentClassificationHistory.created_at)
        .all()
    )
    assert len(history_rows) == 2  # 최초 자동분류 1건 + 연구원 수정 1건
    assert history_rows[-1].changed_by_user_id == reviewer.id
    assert history_rows[-1].new_primary_field_code == FieldCode.CONV
    assert history_rows[-1].reason == "연구원 판단: 융합기술이 더 적절함"
