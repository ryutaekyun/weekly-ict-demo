"""시연 출력물(DOCX·PDF·PPTX·PNG) 열람·서식 검증 — apps/api 가상환경의 python으로 실행한다.

  apps\\api\\.venv\\Scripts\\python scripts\\verify_outputs.py [폴더]      (기본: apps/web/test-results/phase38)

검증 범위는 python-docx·PyMuPDF·python-pptx·Pillow로 파일을 열어 보는 것까지이며, Microsoft Word·PowerPoint에서 직접 연 결과는 확인하지 않았다(미검증).
"""
from __future__ import annotations

import io
import sys as _s
_s.stdout.reconfigure(encoding="utf-8")
import re
import sys
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document
from PIL import Image
from pptx import Presentation

EMU_PER_CM = 360000
folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("apps/web/test-results/phase38")
problems: list[str] = []
checked: list[str] = []


def ok(cond: bool, msg: str):
    (checked if cond else problems).append(("PASS " if cond else "FAIL ") + msg)


def docx_text(p: Path) -> str:
    d = Document(str(p))
    parts = [x.text for x in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    for s in d.sections:
        parts.extend(x.text for x in s.header.paragraphs)
        parts.extend(x.text for x in s.footer.paragraphs)
    return "\n".join(parts)


def check_docx(p: Path):
    d = Document(str(p))
    text = docx_text(p)
    ok(len(d.paragraphs) > 5, f"{p.name}: 문단 {len(d.paragraphs)}개로 열림")
    ok("�" not in text, f"{p.name}: 깨진 글자(U+FFFD) 없음")
    ok("IITP" in text and ("미확인" in text or "확인 전" in text), f"{p.name}: 'IITP 확인 전/미확인' 표시")
    ok("시범" in text or "내부" in text, f"{p.name}: 시범·내부용 표시")
    heads = [x.text.strip() for x in d.paragraphs if x.style.name.lower().startswith(("heading", "제목")) and x.text.strip()]
    ok(len(heads) == len(set(heads)) or len(heads) == 0, f"{p.name}: 같은 제목 중복 없음({len(heads)}개)")
    caps = [x.text.strip() for x in d.paragraphs if re.match(r"^(표|그림)\s*\d+", x.text.strip())]
    ok(len(caps) == len(set(caps)), f"{p.name}: 표·그림 캡션 번호 중복 없음({len(caps)}개)")
    sec = d.sections[0]
    ok(abs(sec.page_width.cm - 21.0) < 0.3 and abs(sec.page_height.cm - 29.7) < 0.3, f"{p.name}: A4 용지({sec.page_width.cm:.1f}×{sec.page_height.cm:.1f}cm)")


def check_pdf(p: Path):
    doc = fitz.open(str(p))
    pages = [pg.get_text() for pg in doc]
    ok(len(doc) >= 2, f"{p.name}: {len(doc)}쪽으로 열림")
    full = "\n".join(pages)
    ok("�" not in full, f"{p.name}: 깨진 글자 없음")
    ok(not (re.search(r"\(20\d\d\.\d{1,2}\.\d{1,2}\.\)", full) and "발표일 미확인" in full), f"{p.name}: 본문 인용의 날짜와 각주의 발표일 표기가 서로 어긋나지 않음")
    ok("IITP" in full, f"{p.name}: IITP 확인 전 표시")
    ok(sum(1 for t in pages if len(t.strip()) < 5) == 0, f"{p.name}: 빈 쪽 없음")
    # 목차 쪽 번호가 실제 해당 제목이 있는 쪽과 맞는지(목차 줄의 '제목 ..... 번호' 형식일 때만 검사)
    toc_hits, mism = 0, 0
    for line in pages[1].splitlines() if len(pages) > 1 else []:
        m = re.match(r"^(.{3,60}?)[\s·.…]{2,}(\d{1,3})\s*$", line.strip())
        if m and "공식 확인 전" not in line:
            toc_hits += 1
            title, no = m.group(1).strip(), int(m.group(2))
            real = [i + 1 for i, t in enumerate(pages) if i > 1 and title[:12] in t]
            if real and no not in real:
                mism += 1
    ok(mism == 0, f"{p.name}: 목차 쪽 번호 불일치 {mism}건(검사 줄 {toc_hits}개)")
    fonts = {f[3] for pg in doc for f in pg.get_fonts()}
    ok(len(fonts) > 0, f"{p.name}: 글꼴 {len(fonts)}종 포함")


def check_pptx(p: Path):
    prs = Presentation(str(p))
    w, h = prs.slide_width / EMU_PER_CM, prs.slide_height / EMU_PER_CM
    ok(abs(w - 7.0) < 0.05 and abs(h - 15.62) < 0.05, f"{p.name}: 슬라이드 {w:.2f}×{h:.2f}cm (기준 7×15.62)")
    n_text = 0
    all_text = ""
    for i, s in enumerate(prs.slides, 1):
        texts = [sh for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
        n_text += len(texts)
        all_text += "\n".join(sh.text_frame.text for sh in texts)
        ok(len(texts) > 0, f"{p.name}: {i}번 슬라이드에 편집 가능한 텍스트 상자 {len(texts)}개")
        pics = [sh for sh in s.shapes if sh.shape_type == 13]
        ok(len(pics) == 0 or len(texts) > 0, f"{p.name}: {i}번 슬라이드가 그림 한 장으로만 구성되지 않음")
    ok("시범" in all_text or "IITP" in all_text, f"{p.name}: 시범·IITP 미확인 표시")
    ok("�" not in all_text, f"{p.name}: 깨진 글자 없음")


def check_png_zip(p: Path):
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".png")]
        ok(len(names) >= 3, f"{p.name}: PNG {len(names)}장")
        for n in names:
            im = Image.open(io.BytesIO(z.read(n)))
            w, h = im.size
            ok(min(w, h) >= 1000 and abs(w / h - 7 / 15.62) < 0.01, f"{p.name}/{n}: {w}×{h}px 비율 7:15.62")


for f in sorted(folder.glob("*")):
    if f.suffix == ".docx":
        check_docx(f)
    elif f.suffix == ".pdf":
        check_pdf(f)
    elif f.suffix == ".pptx":
        check_pptx(f)
    elif f.suffix == ".zip":
        check_png_zip(f)

print("\n".join(checked + problems))
print(f"\n통과 {len(checked)}건, 실패 {len(problems)}건 — Word·PowerPoint 실제 열람 호환은 미검증(LibreOffice·python 라이브러리로만 확인)")
sys.exit(1 if problems else 0)
