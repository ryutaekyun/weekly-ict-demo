"""DOCX → PDF 변환(LibreOffice headless)과 실제 렌더링 기반 페이지 분석(PyMuPDF).

페이지 수·목차 페이지 번호·파트별 분량은 글자 수로 추정하지 않고, 변환된 PDF를 실제로 읽어서 센다.
LibreOffice가 없는 환경에서는 PdfUnavailableError를 올려 '생성 불가'로 정직하게 보고한다(가짜 PDF 없음).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class PdfUnavailableError(RuntimeError):
    pass


def find_soffice() -> str | None:
    env = os.environ.get("SOFFICE_PATH")
    if env and Path(env).exists():
        return env
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "lo_portable" / "program" / "soffice.exe",
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def convert_office_to_pdf(data: bytes, suffix: str = "docx", timeout: int = 240) -> bytes:
    """LibreOffice headless로 DOCX/PPTX 등을 PDF로 변환한다(보고서·카드뉴스 공용)."""
    soffice = find_soffice()
    if soffice is None:
        raise PdfUnavailableError("LibreOffice(soffice)를 찾을 수 없어 PDF를 생성할 수 없습니다")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / f"document.{suffix}"
        src.write_bytes(data)
        profile = tmp_path / "lo_profile"
        cmd = [
            soffice, "--headless", "--norestore", "--nolockcheck",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to", "pdf", "--outdir", str(tmp_path), str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        out = tmp_path / "document.pdf"
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"PDF 변환 실패(code={proc.returncode}): {proc.stderr.decode('utf-8', 'ignore')[:500]}")
        return out.read_bytes()


def convert_docx_to_pdf(docx_bytes: bytes, timeout: int = 180) -> bytes:
    return convert_office_to_pdf(docx_bytes, "docx", timeout)


def _squash(text: str) -> str:
    return "".join(text.split())


def _find_toc_end(page_texts: list[str]) -> int:
    """표지·목차를 건너뛴 본문 시작 페이지 인덱스(0부터). '목 차' 제목이 있는 페이지 다음부터 본문."""
    for idx, text in enumerate(page_texts[:6]):
        if _squash(text).startswith("목차"):
            end = idx
            while end + 1 < len(page_texts) and _squash(page_texts[end + 1]).startswith("목차") is False and (
                page_texts[end + 1].count("....") >= 3
            ):
                end += 1
            return end + 1
    return min(2, len(page_texts))


def analyze_pdf(pdf_bytes: bytes, headings: list[tuple[int, str]], part_headings: list[str]) -> dict:
    """실제 렌더링된 PDF에서 총 페이지 수, 제목별 시작 페이지(1부터), 파트별 페이지 수를 구한다."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_count = doc.page_count
        page_texts = [doc[i].get_text() for i in range(page_count)]
        squashed = [_squash(t) for t in page_texts]
        toc_end = _find_toc_end(page_texts)
        heading_pages: dict[str, int] = {}
        cursor = toc_end
        for _level, text in headings:
            key = text.strip()
            needle = _squash(key)[:30]
            for page_idx in range(cursor, page_count):
                if needle and needle in squashed[page_idx]:
                    heading_pages.setdefault(key, page_idx + 1)
                    cursor = page_idx
                    break
        def at_page_top(page_no: int, heading: str) -> bool:
            """제목이 그 페이지 맨 위(머리글 바로 아래)에서 시작하는가 — 아니면 앞 파트와 같은 페이지를 공유한다."""
            text = page_texts[page_no - 1].strip()
            first_line = text.splitlines()[0] if text else ""
            idx = squashed[page_no - 1].find(_squash(heading)[:30])
            return 0 <= idx <= len(_squash(first_line)) + 1

        starts = [(h, heading_pages.get(h.strip())) for h in part_headings]
        part_pages: list[dict] = []
        for idx, (h, start) in enumerate(starts):
            if start is None:
                part_pages.append({"heading": h, "start_page": None, "pages": None})
                continue
            nxt = next(((nh, ns) for nh, ns in starts[idx + 1:] if ns is not None), None)
            if nxt is None:
                end = page_count
            else:
                end = nxt[1] - 1 if at_page_top(nxt[1], nxt[0]) else nxt[1]
            part_pages.append({"heading": h, "start_page": start, "pages": max(1, end - start + 1)})
        return {
            "page_count": page_count, "heading_pages": heading_pages, "part_pages": part_pages,
            "toc_end_page": toc_end, "text": "\n".join(page_texts),
        }
    finally:
        doc.close()


def render_pages_png(pdf_bytes: bytes, out_dir: Path, zoom: float = 1.4, max_pages: int = 60) -> list[Path]:
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    paths: list[Path] = []
    try:
        for i in range(min(doc.page_count, max_pages)):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            path = out_dir / f"page-{i + 1:02d}.png"
            pix.save(str(path))
            paths.append(path)
    finally:
        doc.close()
    return paths
