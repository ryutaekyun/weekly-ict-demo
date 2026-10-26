"""외부 저자가 올린 파일의 보안 검사와 저장.

- 파일은 서버 로컬 저장소(settings.journal_dir)에만 저장하고 공개 저장소에 올리지 않는다. 내려받기는 인증·권한 확인 후 첨부 파일로만 제공한다.
- 문서 안의 매크로·스크립트·임베디드 개체는 실행하지 않으며, 발견되면 접수를 거부한다(검사 결과는 기록).
- 이 검사는 알려진 위험 요소(매크로·OLE·ActiveX·PDF 스크립트·압축 폭탄·확장자/내용 불일치)를 막는 1차 점검이며 안티바이러스를 대체하지 않는다.
"""

import hashlib
import io
import re
import uuid
import zipfile
from pathlib import Path

from app.core.config import settings

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_BY_EXT = {
    "docx": DOCX_MIME, "pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "txt": "text/plain",
}
MAGIC = {"pdf": b"%PDF-", "png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff", "jpeg": b"\xff\xd8\xff"}
OOXML = ("docx", "xlsx")
MAX_UNCOMPRESSED = 300 * 1024 * 1024  # 압축 해제 합계 상한(압축 폭탄 방지)
MAX_RATIO = 200
PDF_DANGEROUS = (b"/JavaScript", b"/JS", b"/Launch", b"/OpenAction", b"/AA", b"/RichMedia", b"/XFA")
PDF_EMBEDDED = (b"/EmbeddedFile",)


class UploadRejected(Exception):
    """보안·형식 검사에서 거부된 업로드. message는 사용자에게 보여도 되는 사유."""


def journal_root() -> Path:
    root = Path(settings.journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_name(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^\w.\-가-힣 ()\[\]]", "_", base).strip(" .")
    return (base or "file")[:150]


def ext_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def scan_upload(file_name: str, data: bytes, allowed_ext: list[str], max_bytes: int) -> dict:
    """검사 통과 시 결과 dict(ok=True, 경고 포함)를 돌려주고, 거부 사유가 있으면 UploadRejected를 던진다."""
    ext = ext_of(file_name)
    if ext not in allowed_ext:
        raise UploadRejected(f"허용되지 않는 파일 형식입니다(.{ext or '없음'}) — 허용: {', '.join('.' + e for e in allowed_ext)}")
    if not data:
        raise UploadRejected("빈 파일입니다")
    if len(data) > max_bytes:
        raise UploadRejected(f"파일이 너무 큽니다({len(data) / 1024 / 1024:.1f}MB > {max_bytes / 1024 / 1024:.0f}MB)")
    warnings: list[str] = []
    if ext in MAGIC and not data.startswith(MAGIC[ext]):
        raise UploadRejected("파일 내용이 확장자와 일치하지 않습니다")
    if ext in OOXML:
        _scan_ooxml(data, ext, warnings)
    elif ext == "pdf":
        _scan_pdf(data, warnings)
    elif ext == "txt":
        if b"\x00" in data[:4096]:
            raise UploadRejected("텍스트 파일이 아닙니다")
    return {"ok": True, "ext": ext, "size": len(data), "warnings": warnings, "checks": [
        "확장자·내용 일치", "매크로·스크립트·임베디드 개체 검사", "압축 폭탄 검사"]}


def _scan_ooxml(data: bytes, ext: str, warnings: list[str]) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        infos = zf.infolist()
    except zipfile.BadZipFile:
        raise UploadRejected("손상되었거나 올바른 Office 문서가 아닙니다")
    total = sum(i.file_size for i in infos)
    comp = max(sum(i.compress_size for i in infos), 1)
    if total > MAX_UNCOMPRESSED or total / comp > MAX_RATIO:
        raise UploadRejected("압축 해제 크기가 비정상적으로 큽니다(압축 폭탄 의심)")
    if "[Content_Types].xml" not in names:
        raise UploadRejected("올바른 Office 문서가 아닙니다")
    if ext == "docx" and "word/document.xml" not in names:
        raise UploadRejected("Word 문서 본문(word/document.xml)이 없습니다")
    lowered = [n.lower() for n in names]
    if any("vbaproject" in n for n in lowered):
        raise UploadRejected("매크로(VBA)가 포함된 문서는 접수할 수 없습니다 — 매크로를 제거한 .docx로 다시 제출하세요")
    content_types = zf.read("[Content_Types].xml").decode("utf-8", "ignore").lower()
    if "macroenabled" in content_types or "vbaproject" in content_types:
        raise UploadRejected("매크로 사용 문서 형식입니다 — 매크로를 제거한 문서로 제출하세요")
    if any(n.startswith(("word/activex", "xl/activex")) or n.endswith(".bin") and "embeddings" in n for n in lowered):
        raise UploadRejected("ActiveX·임베디드 개체가 포함된 문서는 접수할 수 없습니다")
    if any("/embeddings/" in n for n in lowered):
        raise UploadRejected("임베디드 파일(OLE)이 포함된 문서는 접수할 수 없습니다")
    for n in names:
        if n.endswith(".rels"):
            rels = zf.read(n).decode("utf-8", "ignore")
            if re.search(r'attachedTemplate"[^>]*TargetMode="External"|TargetMode="External"[^>]*attachedTemplate', rels):
                raise UploadRejected("외부 템플릿을 불러오는 문서는 접수할 수 없습니다")
            if re.search(r"(oleObject|externalLink|frame)[^>]*TargetMode=\"External\"", rels):
                raise UploadRejected("외부 개체를 참조하는 문서는 접수할 수 없습니다")
            if "TargetMode=\"External\"" in rels:
                warnings.append("외부 하이퍼링크가 포함되어 있습니다(링크는 자동으로 열리지 않습니다)")
    if any(n.startswith("word/media/") for n in names):
        warnings.append("그림이 포함되어 있습니다 — 자동 변환되지 않으므로 원본 파일로 확인합니다")


def _scan_pdf(data: bytes, warnings: list[str]) -> None:
    head = data[: 4 * 1024 * 1024]
    for token in PDF_DANGEROUS:
        if token in head or token in data[-1024 * 1024:]:
            raise UploadRejected("스크립트·자동 실행 동작이 포함된 PDF는 접수할 수 없습니다")
    if any(t in data for t in PDF_EMBEDDED):
        raise UploadRejected("첨부 파일이 포함된 PDF는 접수할 수 없습니다")
    if b"/Encrypt" in data[-2048:] or b"/Encrypt" in head:
        warnings.append("암호화된 PDF입니다 — 내용을 확인할 수 없을 수 있습니다")


def store(kind: str, parent_id: uuid.UUID, file_name: str, data: bytes) -> tuple[str, str]:
    """파일을 저장하고 (경로, sha256)을 돌려준다. 같은 이름이어도 항상 새 파일로 저장한다(덮어쓰기 없음)."""
    digest = hashlib.sha256(data).hexdigest()
    folder = journal_root() / kind / str(parent_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}_{safe_name(file_name)}"
    path.write_bytes(data)
    return str(path), digest


def read(path: str) -> bytes:
    p = Path(path).resolve()
    root = journal_root().resolve()
    if root not in p.parents:  # 저장소 밖 경로는 읽지 않는다
        raise FileNotFoundError(path)
    return p.read_bytes()
