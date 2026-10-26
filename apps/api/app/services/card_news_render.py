"""PPTX → PDF(LibreOffice) → 카드별 고해상도 PNG, 그리고 실제 렌더링 결과 점검.

PNG는 HTML 화면 캡처가 아니라 PPTX를 실제로 렌더링한 결과라서 PPTX와 레이아웃이 같다.
"""

from app.services import report_pdf


def render_pngs(pptx_bytes: bytes, short_px: int = 1000) -> tuple[list[bytes], bytes, list[tuple[int, int]]]:
    """(카드별 PNG 바이트 목록, 중간 PDF 바이트, 카드별 (가로px, 세로px)). 짧은 변이 short_px 이상이 되도록 렌더링한다."""
    import fitz

    pdf = report_pdf.convert_office_to_pdf(pptx_bytes, "pptx")
    doc = fitz.open(stream=pdf, filetype="pdf")
    pngs: list[bytes] = []
    sizes: list[tuple[int, int]] = []
    try:
        for page in doc:
            rect = page.rect
            zoom = max(short_px / min(rect.width, rect.height), 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pngs.append(pix.tobytes("png"))
            sizes.append((pix.width, pix.height))
    finally:
        doc.close()
    return pngs, pdf, sizes


def check_rendered(pdf_bytes: bytes, scenes: list[dict]) -> list[dict]:
    """렌더링된 PDF에서 (1) 카드 수 일치, (2) 글자가 카드 밖으로 나가는지, (3) 장면의 글이 실제로 그려졌는지 확인한다."""
    import fitz

    issues: list[dict] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count != len(scenes):
            issues.append({"level": "error", "code": "page_count_mismatch",
                           "message": f"렌더링 페이지 수({doc.page_count})가 카드 수({len(scenes)})와 다릅니다", "key": None})
        for idx, page in enumerate(doc):
            if idx >= len(scenes):
                break
            rect = page.rect
            words = page.get_text("words")
            for x0, y0, x1, y1, word, *_ in words:
                if x1 > rect.x1 + 1 or y1 > rect.y1 + 1 or x0 < rect.x0 - 1 or y0 < rect.y0 - 1:
                    issues.append({"level": "error", "code": "rendered_out_of_bounds",
                                   "message": f"{idx + 1}번 카드에서 글자 '{word}'가 카드 밖으로 나갑니다", "key": None})
                    break
            page_text = "".join(page.get_text().split())
            for it in scenes[idx]["items"]:
                if it["type"] != "text" or it.get("placeholder"):
                    continue
                probe = "".join(str(it["text"]).split())[:6]
                if probe and probe not in page_text:
                    issues.append({"level": "warn", "code": "text_not_rendered",
                                   "message": f"{idx + 1}번 카드의 '{it['text'][:12]}…'가 렌더링 결과에서 확인되지 않습니다", "key": it.get("key")})
    finally:
        doc.close()
    return issues
