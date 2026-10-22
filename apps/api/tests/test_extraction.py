import httpx

from app.models.enums import ExtractionMethod, ExtractionStatus
from app.services import extraction as extraction_service


def _fake_client(response_text="", content_type="text/html", status_ok=True, raise_exc=None):
    class FakeResponse:
        text = response_text
        content = response_text.encode("utf-8")
        headers = {"content-type": content_type, "content-length": str(len(response_text))}

        def raise_for_status(self):
            if raise_exc:
                raise raise_exc

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return FakeResponse()

    return FakeClient()


def test_html_extraction_picks_article_tag_and_strips_nav(monkeypatch):
    html = """
    <html><body>
      <nav>Home | About | Contact</nav>
      <article>
        <p>This is the real article content that matters for ICT policy analysis and should be extracted.</p>
        <p>A second paragraph with more substantive detail about the technology trend being discussed here.</p>
      </article>
      <footer>Copyright 2026</footer>
    </body></html>
    """
    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: True)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _fake_client(html))

    result = extraction_service.extract_html_full_text("https://example.org/article")

    assert result.status == ExtractionStatus.SUCCESS
    assert result.method == ExtractionMethod.HTML
    assert "Home | About | Contact" not in result.full_text
    assert "Copyright 2026" not in result.full_text
    assert "real article content" in result.full_text


def test_html_extraction_respects_robots_disallow(monkeypatch):
    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: False)

    result = extraction_service.extract_html_full_text("https://example.org/blocked")

    assert result.status == ExtractionStatus.NOT_ATTEMPTED
    assert result.full_text is None
    assert "robots" in result.failure_reason


def test_html_extraction_too_short_is_marked_failed_not_success(monkeypatch):
    html = "<html><body><article><p>Too short.</p></article></body></html>"
    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: True)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _fake_client(html))

    result = extraction_service.extract_html_full_text("https://example.org/short")

    assert result.status == ExtractionStatus.FAILED


def test_pdf_extraction_scanned_pdf_is_not_marked_success(monkeypatch):
    """텍스트 레이어가 거의 없는(스캔본으로 추정되는) PDF는 SUCCESS로 표시하지 않는다."""

    class FakePage:
        def extract_text(self):
            return ""  # 스캔본 — 텍스트 레이어 없음

    class FakeReader:
        def __init__(self, _bytes):
            self.pages = [FakePage(), FakePage(), FakePage()]

    monkeypatch.setattr(extraction_service, "PdfReader", FakeReader)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _fake_client("fake-pdf-bytes", content_type="application/pdf"))

    result = extraction_service.extract_pdf_full_text("https://example.org/scanned.pdf")

    assert result.status in (ExtractionStatus.FAILED,)
    assert "스캔본" in result.failure_reason or "읽지 못함" in result.failure_reason


def test_pdf_extraction_with_real_text_succeeds(monkeypatch):
    sample_text = "This is a real extracted paragraph with substantial content. " * 5

    class FakePage:
        def extract_text(self):
            return sample_text

    class FakeReader:
        def __init__(self, _bytes):
            self.pages = [FakePage(), FakePage()]

    monkeypatch.setattr(extraction_service, "PdfReader", FakeReader)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _fake_client("fake-pdf-bytes", content_type="application/pdf"))

    result = extraction_service.extract_pdf_full_text("https://example.org/real.pdf")

    assert result.status == ExtractionStatus.SUCCESS
    assert result.method == ExtractionMethod.PDF
    assert result.char_count > 0


def test_derive_arxiv_pdf_url():
    assert extraction_service.derive_arxiv_pdf_url("https://arxiv.org/abs/2610.12345") == "https://arxiv.org/pdf/2610.12345"
    assert extraction_service.derive_arxiv_pdf_url("https://example.org/page") is None


def test_http_failure_is_marked_failed_with_reason(monkeypatch):
    def raise_error(**kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://example.org"))

    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: True)
    monkeypatch.setattr(httpx, "Client", raise_error)

    result = extraction_service.extract_html_full_text("https://example.org/unreachable")

    assert result.status == ExtractionStatus.FAILED
    assert result.failure_reason is not None
