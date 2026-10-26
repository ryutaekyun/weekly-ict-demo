"""Phase 3-2 시범 보고서·요약본 출력 생성(개발용 출력 테스트).

- 일반호/요약본: Phase 3-1의 FMVSS 305a '시범 작성 원고'(실제 공식 원문 기반)를 그대로 사용한다.
  미검증 각주 1건은 임의로 검증 완료 처리하지 않고, 배치되지 않은 파트는 비워 '미완성 초안'으로 출력한다.
- 특집호·확정 흐름: '[합성 테스트 데이터]' 원고를 새로 만들어 사용한다(데이터 성격을 제목·본문에 명시).
- 실제 IITP 발간물이 아니며, 생성된 파일은 서버 로컬 저장소(storage/exports)에만 있다.

실행: python -m app.create_pilot_reports [출력폴더]
"""

import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.db import SessionLocal
from app.models.enums import EvidenceMatchStatus, ManuscriptStatus
from app.models.manuscript import Manuscript
from app.models.approval import Approval
from app.models.manuscript_comment import ManuscriptComment
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.manuscript_version import ManuscriptVersion
from app.models.report import Report, ReportExport, ReportItem
from app.models.user import User
from app.create_pilot_manuscript import ANCHORS
from app.services import manuscript_footnote_service, manuscript_service, report_pdf, report_service

SYN = "[합성 테스트 데이터]"


def _t(text, fn=None, marks=None):
    node = {"type": "text", "text": text}
    all_marks = list(marks or [])
    if fn:
        all_marks.append({"type": "footnoteMark", "attrs": {"footnoteId": fn}})
    if all_marks:
        node["marks"] = all_marks
    return node


def _p(*nodes):
    return {"type": "paragraph", "content": list(nodes)}


def _h(level, text):
    return {"type": "heading", "attrs": {"level": level}, "content": [_t(text)]}


def _cell(kind, text):
    return {"type": kind, "attrs": {"colspan": 1, "rowspan": 1}, "content": [_p(_t(text))]}


def _table(header, rows):
    out = [{"type": "tableRow", "content": [_cell("tableHeader", h) for h in header]}]
    for r in rows:
        out.append({"type": "tableRow", "content": [_cell("tableCell", c) for c in r]})
    return {"type": "table", "content": out}


def _plain(doc):
    out = []

    def walk(n):
        if n.get("type") == "text":
            out.append(n["text"])
        for c in n.get("content", []):
            walk(c)
        if n.get("type") in ("paragraph", "heading"):
            out.append("\n")

    walk(doc)
    return "".join(out).strip()


def _make_synthetic(db, author, reviewer, approver, *, title, paragraphs, long_table_rows=0, tag):
    ms = manuscript_service.create_manuscript(db, author_user_id=author.id, title=title, manuscript_type="key_issue", is_pilot=True)
    ms.title_en = f"{SYN} Synthetic manuscript for output testing ({tag})"
    marks = [str(uuid.uuid4()) for _ in paragraphs]
    blocks = [_h(1, title), _h(2, "1. 개요(합성 데이터)")]
    for idx, text in enumerate(paragraphs):
        blocks.append(_p(_t(text, marks[idx])))
    blocks.append(_h(2, "2. 비교표(합성 데이터)"))
    blocks.append(_table(["항목", "A국", "B국", "비고"], [[f"항목 {i}", f"{i * 3}%", f"{i * 2}%", "합성 수치"] for i in range(1, 5 + long_table_rows)]))
    blocks.append({"type": "bulletList", "content": [
        {"type": "listItem", "content": [_p(_t("합성 글머리 항목 1: "), _t("굵은 강조", marks=[{"type": "bold"}]))]},
        {"type": "listItem", "content": [_p(_t("합성 글머리 항목 2: 링크 "), _t("예시 링크", marks=[{"type": "link", "attrs": {"href": "https://example.org/synthetic"}}]))]},
    ]})
    doc = {"type": "doc", "content": blocks}
    manuscript_service.update_manuscript_body(
        db, ms, title=None, title_en=None, body_json=json.dumps(doc, ensure_ascii=False), body=_plain(doc),
        lock_version=ms.lock_version, actor_user_id=author.id, change_note=f"{SYN} 생성", is_milestone=True,
    )
    for idx, text in enumerate(paragraphs):
        fn = manuscript_footnote_service.create_footnote(
            db, manuscript_id=ms.id, created_by_user_id=author.id, mark_id=marks[idx], anchor_text=text,
            source_url=f"https://example.org/synthetic-source-{tag}-{idx + 1}", source_org="합성 기관(테스트)",
            location_label=f"{idx + 1}문단",
        )
        fn.verification_status = EvidenceMatchStatus.MATCHED  # 합성 데이터의 검증 흐름 테스트용
        fn.verified_by_user_id = reviewer.id
        fn.verified_at = datetime.now(timezone.utc)
    manuscript_service.request_review(db, ms, reviewer_user_id=reviewer.id)
    manuscript_service.approve_internal(db, ms, approver_user_id=approver.id, comment=f"{SYN} 흐름 테스트 승인")
    return ms


def _cleanup_previous_outputs(db) -> None:
    """이 스크립트가 이전에 만든 시범 보고서·합성 원고를 지워 다시 실행해도 중복이 쌓이지 않게 한다(실제 원고는 건드리지 않음)."""
    reports = db.query(Report).filter(
        (Report.title.like("[시범] 주간%")) | (Report.title.like(f"{SYN}%"))
    ).all()
    for r in reports:
        for exp in db.query(ReportExport).filter_by(report_id=r.id).all():
            if exp.file_path:
                Path(exp.file_path).unlink(missing_ok=True)
            db.delete(exp)
        for it in db.query(ReportItem).filter_by(report_id=r.id).all():
            db.delete(it)
        db.delete(r)
    db.flush()
    for ms in db.query(Manuscript).filter(Manuscript.title.like(f"{SYN}%")).all():
        for model in (ManuscriptFootnote, ManuscriptVersion, ManuscriptComment):
            for row in db.query(model).filter_by(manuscript_id=ms.id).all():
                db.delete(row)
        for ap in db.query(Approval).filter_by(approvable_id=ms.id).all():
            db.delete(ap)
        db.delete(ms)
    db.commit()


def _new_report(db, user, rtype, title, title_en=None):
    template = report_service.get_active_template(db)
    r = Report(report_type=rtype, title=title, title_en=title_en, template_id=template.id, created_by_user_id=user.id)
    db.add(r)
    db.flush()
    return r


def _add(db, report, part_key, ms, heading=None):
    pos = db.query(ReportItem).filter_by(report_id=report.id).count() + 1
    db.add(ReportItem(report_id=report.id, position=pos, part_key=part_key, manuscript_id=ms.id, heading=heading))
    db.flush()


def _export_both(db, report, user, out: Path, prefix: str, final=False):
    results = {}
    for fmt in ("docx", "pdf"):
        exp = report_service.generate_export(db, report, file_format=fmt, user_id=user.id, final=final)
        if exp.status != "success":
            raise SystemExit(f"{prefix} {fmt} 생성 실패: {exp.error_message}")
        target = out / f"{prefix}.{fmt}"
        shutil.copy(exp.file_path, target)
        results[fmt] = exp
        print(f"  {prefix}.{fmt}: {exp.file_size}B, 페이지 {exp.page_count}, 각주 {exp.footnote_count}, 표 {exp.table_count}")
    pdf_bytes = Path(out / f"{prefix}.pdf").read_bytes()
    report_pdf.render_pages_png(pdf_bytes, out / f"{prefix}_pages")
    return results


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pilot_outputs")
    out.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        author = db.query(User).filter_by(email="dev-researcher-1@example.com").one()
        reviewer = db.query(User).filter_by(email="dev-reviewer-1@example.com").one()
        approver = db.query(User).filter_by(email="dev-admin@example.com").one()
        pilot = db.query(Manuscript).filter(Manuscript.title.like("[시범] 미국 NHTSA%")).first()
        if pilot is None:
            raise SystemExit("먼저 python -m app.create_pilot_manuscript 로 시범 원고를 만드세요")
        _cleanup_previous_outputs(db)
        # Phase 3-1 시범 원고의 각주 anchor_text를 실제 문장으로 보정(초기에는 내부 키가 들어가 있었음)
        for fn in db.query(ManuscriptFootnote).filter_by(manuscript_id=pilot.id).all():
            if fn.anchor_text in ANCHORS:
                fn.anchor_text = ANCHORS[fn.anchor_text]
        db.commit()

        print("1) 일반호(시범 원고 1건, 나머지 파트는 미완성으로 비워 둠)")
        general = _new_report(db, author, "general", "[시범] 주간 AI·ICT 동향 일반호 — 개발용 출력 테스트", "[Pilot] Weekly AI·ICT Trends — Output Test")
        _add(db, general, "key_issue", pilot)
        db.commit()
        _export_both(db, general, author, out, "01_일반호_시범")

        print("2) 일반호 요약본(시범 원고의 문장을 연구원이 선택·편집)")
        summary = _new_report(db, author, "summary", "[시범] 주간 AI·ICT 동향 요약본 — 개발용 출력 테스트")
        lines = [ln.strip() for ln in (pilot.body or "").splitlines() if len(ln.strip()) >= 12]
        picks = [ln for ln in lines if "공고함" in ln][:1] + [ln for ln in lines if "시행됨" in ln][:1]
        for pos, sentence in enumerate(picks, start=1):
            db.add(ReportItem(report_id=summary.id, position=pos, part_key="key_issue", manuscript_id=pilot.id,
                              source_sentence=sentence, summary_text=sentence))
        db.add(ReportItem(report_id=summary.id, position=len(picks) + 1, part_key="key_message", manuscript_id=pilot.id,
                          source_sentence=lines[1] if len(lines) > 1 else lines[0],
                          summary_text="핵심 메시지(연구원 작성 예시): 시행일과 준수 시한을 구분해 일정을 관리할 필요가 있음."))
        db.commit()
        _export_both(db, summary, author, out, "02_요약본_시범")

        print("2b) 같은 내용의 간결형 요약본(표지·목차 없이 1~2쪽)")
        compact = _new_report(db, author, "summary", "[시범] 주간 AI·ICT 동향 요약본(간결형) — 개발용 출력 테스트")
        compact.layout = "compact"
        for it in db.query(ReportItem).filter_by(report_id=summary.id).order_by(ReportItem.position).all():
            db.add(ReportItem(report_id=compact.id, position=it.position, part_key=it.part_key, manuscript_id=it.manuscript_id,
                              source_sentence=it.source_sentence, summary_text=it.summary_text))
        db.commit()
        _export_both(db, compact, author, out, "02b_요약본_간결형_시범")

        print("3) 합성 원고 생성(특집호·긴 문서·확정 흐름 검증용)")
        syn_a = _make_synthetic(db, author, reviewer, approver, title=f"{SYN} 특집 원고 A — 긴 표 포함",
                                paragraphs=[f"합성 문장 {i}: 출력 레이아웃 점검을 위한 가상의 설명 문장으로 실제 사실이 아님." for i in range(1, 9)],
                                long_table_rows=34, tag="a")
        syn_b = _make_synthetic(db, author, reviewer, approver, title=f"{SYN} 특집 원고 B",
                                paragraphs=[f"합성 문장 {i}: 두 번째 원고의 가상 설명 문장으로 실제 사실이 아님." for i in range(1, 4)], tag="b")
        db.commit()

        print("4) 특집호(합성 데이터 2건, 소제목 지정)")
        special = _new_report(db, author, "special", f"{SYN} 특집호 출력 테스트")
        _add(db, special, "free", syn_a, heading="첫 번째 특집 주제(소제목 지정 예시)")
        _add(db, special, "free", syn_b)
        db.commit()
        _export_both(db, special, author, out, "03_특집호_합성")

        print("5) 일반호 확정 흐름(합성 원고·모든 각주 검증·내부 승인 → 확정 → 확정본 출력)")
        final_rep = _new_report(db, author, "general", f"{SYN} 일반호 확정 흐름 테스트")
        _add(db, final_rep, "key_issue", syn_a)
        _add(db, final_rep, "country_trend", syn_b)
        db.commit()
        issues = report_service.run_preflight(report_service.build_snapshot(db, final_rep))
        blocking = report_service.blocking_issues(issues)
        print("  확정 차단 항목:", [b["code"] for b in blocking])
        if blocking:
            raise SystemExit("합성 흐름이 확정 점검을 통과해야 합니다")
        final_rep.status = "final"
        final_rep.finalized_by_user_id = approver.id
        final_rep.finalized_at = datetime.now(timezone.utc)
        db.commit()
        _export_both(db, final_rep, author, out, "04_일반호_확정흐름_합성", final=True)
        print("완료:", out.resolve())
    finally:
        db.close()


if __name__ == "__main__":
    main()
