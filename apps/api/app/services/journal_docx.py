"""저자 DOCX/PDF에서 내용을 추출·비교·점검하고, 발간 출력용 에디터 JSON(TipTap 형식)으로 변환한다.

한계(보고 시 그대로 밝힌다):
- 표 서식(셀 병합 등)·그림·각주·수식·변경내용 추적은 자동 변환하지 않는다. 그런 요소가 있으면 '원본 파일 비교 필요'로 표시하고 원본은 그대로 보존한다.
- PDF는 텍스트만 추출하며 표·그림 수는 알 수 없다(None).
"""

import difflib
import io
import re
import zipfile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

CAPTION_RE = re.compile(r"^\s*[\[\(<]?\s*(표|그림|Table|Figure|Fig\.?)\s*(\d+(?:[-.]\d+)?)\s*[\]\)>]?\s*[.:\-–]?\s*(.*)$", re.IGNORECASE)
REF_HEAD_RE = re.compile(r"^\s*(\d+\s*[.)]?\s*)?(참고\s*문헌|참고자료|인용\s*문헌|references?|bibliography)\s*$", re.IGNORECASE)


def _norm(s: str) -> str:
    return " ".join((s or "").split())


def _count_words(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------- 추출 ----
def extract(data: bytes, ext: str) -> dict:
    """문단 텍스트와 통계를 추출한다. 실패하면 ok=False와 사유를 돌려준다(접수는 막지 않는다 — 원본 파일 비교로 확인)."""
    try:
        if ext == "docx":
            return _extract_docx(data)
        if ext == "pdf":
            return _extract_pdf(data)
    except Exception as exc:  # 손상된 문서 등 — 원본 보존, 비교 불가로 표시
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300], "paragraphs": [], "words": 0, "tables": None, "figures": None,
                "needs_original_compare": True}
    return {"ok": False, "error": "텍스트 추출을 지원하지 않는 형식입니다", "paragraphs": [], "words": 0, "tables": None, "figures": None,
            "needs_original_compare": True}


def _extract_docx(data: bytes) -> dict:
    doc = Document(io.BytesIO(data))
    paras: list[dict] = []
    headings: list[str] = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name if p.style is not None else "") or ""
        level = None
        m = re.match(r"(?i)^(heading|제목)\s*(\d)", style)
        if m:
            level = int(m.group(2))
            headings.append(text)
        paras.append({"text": text, "style": style, "level": level})
    tables = len(doc.tables)
    figures = len(doc.inline_shapes)
    zf = zipfile.ZipFile(io.BytesIO(data))
    footnote_count = 0
    if "word/footnotes.xml" in zf.namelist():
        footnote_count = max(zf.read("word/footnotes.xml").decode("utf-8", "ignore").count("<w:footnote ") - 2, 0)  # 구분선 2개 제외
    tracked = False
    xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    if "<w:ins " in xml or "<w:del " in xml:
        tracked = True
    core_title = (doc.core_properties.title or "").strip()
    text_all = "\n".join(p["text"] for p in paras)
    table_texts = []
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                table_texts.append(cell.text)
    words = _count_words(text_all) + _count_words(" ".join(table_texts))
    unsupported = []
    if figures:
        unsupported.append(f"그림 {figures}개")
    if footnote_count:
        unsupported.append(f"각주 {footnote_count}개")
    if tracked:
        unsupported.append("변경내용 추적 기록")
    return {
        "ok": True, "paragraphs": [p["text"] for p in paras], "para_meta": paras, "headings": headings, "words": words, "chars": len(text_all),
        "tables": tables, "figures": figures, "footnotes": footnote_count, "tracked_changes": tracked, "core_title": core_title,
        "unsupported": unsupported,
        # 표·그림·각주·변경내용 추적이 있으면 자동 비교·변환이 불완전하므로 원본 비교 필요로 표시한다
        "needs_original_compare": bool(unsupported),
    }


def _extract_pdf(data: bytes) -> dict:
    import fitz  # PyMuPDF

    pdf = fitz.open(stream=data, filetype="pdf")
    paras: list[str] = []
    for page in pdf:
        for block in page.get_text("blocks"):
            text = _norm(block[4]) if len(block) > 4 else ""
            if text:
                paras.append(text)
    text_all = "\n".join(paras)
    return {"ok": True, "paragraphs": paras, "para_meta": [{"text": t, "style": "", "level": None} for t in paras], "headings": [],
            "words": _count_words(text_all), "chars": len(text_all), "tables": None, "figures": None, "footnotes": None,
            "tracked_changes": False, "core_title": (pdf.metadata or {}).get("title") or "", "pages": len(pdf),
            "unsupported": ["PDF는 표·그림 수를 알 수 없음"], "needs_original_compare": True}


# ---------------------------------------------------------------- 비교 ----
def diff_paragraphs(old: list[str], new: list[str]) -> list[dict]:
    """문단 단위 비교. replace에는 문단 유사도(0~1)를 함께 준다."""
    sm = difflib.SequenceMatcher(a=[_norm(x) for x in old], b=[_norm(x) for x in new], autojunk=False)
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                a = old[i1 + k] if i1 + k < i2 else None
                b = new[j1 + k] if j1 + k < j2 else None
                if a is not None and b is not None:
                    out.append({"type": "modified", "old": a, "new": b, "old_index": i1 + k, "new_index": j1 + k,
                                "similarity": round(difflib.SequenceMatcher(a=_norm(a), b=_norm(b)).ratio(), 2)})
                elif a is not None:
                    out.append({"type": "deleted", "old": a, "old_index": i1 + k})
                else:
                    out.append({"type": "added", "new": b, "new_index": j1 + k})
        elif tag == "delete":
            out += [{"type": "deleted", "old": old[i], "old_index": i} for i in range(i1, i2)]
        elif tag == "insert":
            out += [{"type": "added", "new": new[j], "new_index": j} for j in range(j1, j2)]
    return out


def compare_versions(old_ex: dict, new_ex: dict) -> dict:
    """두 버전의 추출 결과 비교. 자동 비교가 불완전하면 원본 비교 필요 사유를 함께 돌려준다."""
    reasons: list[str] = []
    if not old_ex.get("ok") or not new_ex.get("ok"):
        reasons.append("한쪽 파일에서 텍스트를 추출하지 못했습니다")
    for label, key in (("표", "tables"), ("그림", "figures"), ("각주", "footnotes")):
        a, b = old_ex.get(key), new_ex.get(key)
        if a is None or b is None:
            continue
        if a != b:
            reasons.append(f"{label} 수가 달라졌습니다({a}개 → {b}개) — 변경 내용은 원본 파일로 확인해야 합니다")
        elif a:
            reasons.append(f"{label} {a}개가 있으나 내용 변경 여부는 자동 비교하지 않습니다 — 원본 파일로 확인하세요")
    for ex, name in ((old_ex, "이전"), (new_ex, "이번")):
        if ex.get("tracked_changes"):
            reasons.append(f"{name} 파일에 변경내용 추적 기록이 있어 자동 비교가 부정확할 수 있습니다")
    if "pages" in old_ex or "pages" in new_ex:
        reasons.append("PDF는 표·그림 변경을 자동 비교하지 않습니다 — 원본 파일로 확인하세요")
    changes = diff_paragraphs(old_ex.get("paragraphs", []), new_ex.get("paragraphs", []))
    counts = {k: sum(1 for c in changes if c["type"] == k) for k in ("added", "deleted", "modified")}
    return {"changes": changes, "counts": counts, "needs_original_compare": bool(reasons),
            "original_compare_reasons": reasons, "words": {"old": old_ex.get("words"), "new": new_ex.get("words")},
            "identical_text": not changes}


def map_comments(comments: list[dict], old_paras: list[str], new_paras: list[str]) -> list[dict]:
    """검토 의견이 가리킨 문단이 수정본에서 바뀌었는지 대응 관계를 보여준다. 수정된 것으로 '확정'하지 않고 근거만 제시한다."""
    old_n = [_norm(p) for p in old_paras]
    new_n = [_norm(p) for p in new_paras]
    out = []
    for c in comments:
        anchor = _norm(c.get("anchor_text") or "")
        if not anchor:
            out.append({**c, "match": "doc_level", "note": "문서 전체 의견 — 문단 대응 없음(저자 답변·수정본으로 확인)"})
            continue
        in_old = any(anchor in p or p in anchor for p in old_n if p)
        in_new = any(anchor in p or p in anchor for p in new_n if p)
        if in_old and in_new:
            note, match = "지적한 문단이 수정본에도 그대로 있습니다 — 수정되지 않았을 수 있습니다", "unchanged"
        elif in_old and not in_new:
            note, match = "지적한 문단이 수정본에서 바뀌었거나 삭제되었습니다 — 내용 확인 필요", "changed"
        else:
            note, match = "이전 파일에서 지적한 문단을 찾지 못했습니다 — 원본 파일로 확인하세요", "not_found"
        out.append({**c, "match": match, "note": note})
    return out


# ---------------------------------------------------------------- 형식 점검 ----
def format_check(ex: dict, meta: dict, cfg: dict, attachments: list[str]) -> dict:
    """접수 원고의 형식 점검. 기준값(분량·제출서류)은 관리자가 설정한 것만 쓰며, 미설정이면 '기준 미설정'으로 표시한다."""
    items: list[dict] = []

    def add(key, label, status, detail):
        items.append({"key": key, "label": label, "status": status, "detail": detail})

    title = (meta.get("title") or "").strip()
    add("title", "원고 제목", "pass" if title else "fail", title or "제목이 없습니다")
    en = (meta.get("title_en") or "").strip()
    add("title_en", "영문 제목", "pass" if en else "warn", en or "영문 제목이 없습니다(필수 여부는 모집 안내 확인)")
    authors = meta.get("authors") or []
    ok_auth = bool(authors) and all(a.get("name") and a.get("affiliation") for a in authors)
    add("authors", "저자·소속", "pass" if ok_auth else "fail", "저자와 소속이 모두 입력됨" if ok_auth else "저자 이름과 소속을 모두 입력해야 합니다")
    add("summary", "원고 요약", "pass" if (meta.get("summary") or "").strip() else "warn", "" if (meta.get("summary") or "").strip() else "요약이 없습니다")
    if not ex.get("ok"):
        add("extract", "본문 추출", "warn", f"본문을 자동으로 읽지 못했습니다 — 원본 파일 확인 필요 ({ex.get('error', '')})")
    else:
        paras = ex.get("paragraphs", [])
        has_ref = bool((meta.get("references_text") or "").strip()) or any(REF_HEAD_RE.match(p) for p in paras)
        add("references", "참고문헌", "pass" if has_ref else "warn", "참고문헌 있음" if has_ref else "참고문헌 항목을 찾지 못했습니다")
        words = ex.get("words", 0)
        lo, hi = cfg.get("word_min"), cfg.get("word_max")
        if lo is None and hi is None:
            add("length", "본문 분량", "info", f"{words}단어 — 분량 기준이 설정되지 않았습니다(해당 연도 모집 안내 확인 후 관리자가 설정)")
        else:
            bad = (lo is not None and words < lo) or (hi is not None and words > hi)
            add("length", "본문 분량", "fail" if bad else "pass", f"{words}단어 (기준 {lo or '-'}~{hi or '-'})")
        _caption_checks(paras, add)
    required = cfg.get("required_docs") or []
    if not required:
        add("required_docs", "제출서류", "info", "제출서류 기준이 설정되지 않았습니다(해당 연도 공식 양식 확인 후 관리자가 설정)")
    else:
        missing = [d["label"] for d in required if d["key"] not in attachments]
        add("required_docs", "제출서류", "fail" if missing else "pass", ("누락: " + ", ".join(missing)) if missing else "필수 제출서류 모두 제출")
    fails = [i for i in items if i["status"] == "fail"]
    return {"items": items, "needs_fix": bool(fails), "fail_count": len(fails),
            "warn_count": sum(1 for i in items if i["status"] == "warn"), "result": "needs_fix" if fails else "ok"}


def _caption_checks(paras: list[str], add) -> None:
    seen: dict[str, list[str]] = {"표": [], "그림": []}
    for p in paras:
        m = CAPTION_RE.match(p)
        if not m or len(p) > 200:
            continue
        kind = "표" if m.group(1) in ("표", "Table", "table", "TABLE") or m.group(1).lower() == "table" else "그림"
        seen[kind].append(m.group(2))
    for kind, nums in seen.items():
        if not nums:
            continue
        dup = {n for n in nums if nums.count(n) > 1}
        try:
            expected = [str(i) for i in range(1, len(nums) + 1)]
            seq_ok = nums == expected or all("-" in n or "." in n for n in nums)
        except Exception:
            seq_ok = True
        if dup:
            add(f"caption_{kind}", f"{kind} 번호", "fail", f"{kind} 번호 중복: {', '.join(sorted(dup))}")
        elif not seq_ok:
            add(f"caption_{kind}", f"{kind} 번호", "warn", f"{kind} 번호가 연속되지 않습니다({', '.join(nums)})")
        else:
            add(f"caption_{kind}", f"{kind} 번호·제목", "pass", f"{kind} {len(nums)}개")


# ---------------------------------------------------------------- 발간 출력용 변환 ----
def _run_marks(run) -> list[dict]:
    marks = []
    if run.bold:
        marks.append({"type": "bold"})
    if run.italic:
        marks.append({"type": "italic"})
    if run.underline:
        marks.append({"type": "underline"})
    return marks


def _para_content(p: Paragraph) -> list[dict]:
    out = []
    for run in p.runs:
        if not run.text:
            continue
        node = {"type": "text", "text": run.text}
        marks = _run_marks(run)
        if marks:
            node["marks"] = marks
        out.append(node)
    return out


def to_editor_json(data: bytes) -> tuple[dict, list[str]]:
    """DOCX 본문을 편집기(TipTap) JSON으로 변환한다. 변환하지 못한 요소 목록을 함께 돌려준다."""
    doc = Document(io.BytesIO(data))
    body = doc.element.body
    blocks: list[dict] = []
    skipped: list[str] = []
    list_buf: list[dict] = []
    list_kind = None

    def flush_list():
        nonlocal list_buf, list_kind
        if list_buf:
            blocks.append({"type": "orderedList" if list_kind == "ordered" else "bulletList", "content": list_buf})
        list_buf, list_kind = [], None

    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            content = _para_content(p)
            if not content:
                if child.xpath(".//w:drawing | .//w:pict"):
                    skipped.append("그림")
                continue
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"(?i)^(heading|제목)\s*(\d)", style)
            if m:
                flush_list()
                blocks.append({"type": "heading", "attrs": {"level": min(int(m.group(2)), 3)}, "content": content})
            elif style.lower().startswith("list"):
                kind = "ordered" if "number" in style.lower() else "bullet"
                if list_kind not in (None, kind):
                    flush_list()
                list_kind = kind
                list_buf.append({"type": "listItem", "content": [{"type": "paragraph", "content": content}]})
            else:
                flush_list()
                blocks.append({"type": "paragraph", "content": content})
        elif tag == "tbl":
            flush_list()
            table = Table(child, doc)
            rows = []
            for r_idx, row in enumerate(table.rows):
                cells = []
                seen = set()
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        skipped.append("병합 셀")
                        continue
                    seen.add(id(cell._tc))
                    txt = cell.text.strip()
                    para = {"type": "paragraph", "content": [{"type": "text", "text": txt}] if txt else []}
                    cells.append({"type": "tableHeader" if r_idx == 0 else "tableCell", "content": [para]})
                rows.append({"type": "tableRow", "content": cells})
            if rows:
                blocks.append({"type": "table", "content": rows})
    flush_list()
    return {"type": "doc", "content": blocks}, sorted(set(skipped))
