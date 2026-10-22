from app.services import structured_extract as structured_extract_service


def test_first_paragraphs_skips_unrelated_leading_boilerplate_using_summary_anchor():
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — 연방관보 PDF는 인쇄판 지면을 그대로 잘라
    제공해서 직전의 무관한 고시 꼬리 문단이 앞에 섞여 들어온다. 'SUMMARY:' 필드를 찾으면
    그 뒤를 핵심 내용으로 써야 한다."""
    text = (
        "103788 Federal Register / Vol. 89, No. 244 / Thursday, December 19, 2024 / Notices\n\n"
        "Special Accommodations\nThe meeting is physically accessible to people with disabilities. "
        "This is the tail end of an unrelated prior fishery notice about anadromous fish permits.\n\n"
        "AGENCY: National Telecommunications and Information Administration.\n\n"
        "ACTION: Notice of public meetings.\n\n"
        "SUMMARY: NTIA announces regional roundtables on broadband program sustainability under the "
        "BroadbandUSA initiative to discuss long-term funding models for digital equity programs."
    )

    result = structured_extract_service.extract_structured_rule_based(text=text, source=_FakeSource())

    assert "fishery" not in result["key_content"].lower()
    assert "anadromous" not in result["key_content"].lower()
    assert "broadband" in result["key_content"].lower()


def test_first_paragraphs_falls_back_to_start_when_no_summary_field():
    text = "This is an arXiv-style abstract with no SUMMARY field at all, just the paper's own abstract text here."

    result = structured_extract_service.extract_structured_rule_based(text=text, source=_FakeSource())

    assert "arXiv-style abstract" in result["key_content"]


class _FakeSource:
    org_name = "Test Org"
