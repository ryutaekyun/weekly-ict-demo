"""Phase 3-3 시범 카드뉴스 4종(PPTX·PNG) 생성 — 개발용 출력 테스트.

- A형(핵심 요약)·B형(추진 일정): Phase 3-1/3-2의 FMVSS 305a '시범 작성 원고'(실제 공식 원문 기반)를 보고서에서 가져와 사용한다.
  미검증 각주(2027.9.1. 준수 시한)는 카드에서도 검증 완료로 바꾸지 않는다. 원고에 없는 내용은 '추가 조사 필요'로 남긴다.
- C형(국가 비교)·D형(수치 그래프): 실제 자료가 부족해 '[합성 테스트 데이터]'로 명확히 표시한 가상 자료를 쓴다.
- 실제 IITP 발간물이 아니며 파일은 서버 로컬 저장소와 지정한 출력 폴더에만 있다.

실행: python -m app.create_pilot_card_news [출력폴더]   (먼저 create_pilot_manuscript → create_pilot_reports 실행)
"""

import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.card_news import (
    CardNews, CardNewsCard, CardNewsElement, CardNewsEvidence, CardNewsExport, CardNewsReview, CardNewsVersion,
)
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.report import Report
from app.models.user import User
from app.services import card_news_service as svc

SYN = "[합성 테스트 데이터]"


def _cleanup(db) -> None:
    for cn in db.query(CardNews).filter((CardNews.title.like("[시범] 카드뉴스%")) | (CardNews.title.like(f"{SYN} 카드뉴스%"))).all():
        for exp in db.query(CardNewsExport).filter_by(card_news_id=cn.id).all():
            if exp.file_path:
                Path(exp.file_path).unlink(missing_ok=True)
            shutil.rmtree(svc.export_dir() / f"{exp.id}_png", ignore_errors=True)
            db.delete(exp)
        for model in (CardNewsEvidence, CardNewsReview, CardNewsVersion):
            for row in db.query(model).filter_by(card_news_id=cn.id).all():
                db.delete(row)
        for card in db.query(CardNewsCard).filter_by(card_news_id=cn.id).all():
            for el in db.query(CardNewsElement).filter_by(card_id=card.id).all():
                db.delete(el)
            db.delete(card)
        db.delete(cn)
    db.commit()


def _els(db, card):
    return svc._elements(db, card)


def _set(el, text=None, data=None):
    if text is not None:
        el.text = text
    if data is not None:
        el.data_json = json.dumps(data, ensure_ascii=False)


def _verify(db, cn, card, key, reviewer):
    """카드 내용과 원문 근거를 대조해 검증 완료로 표시한다(원고 각주가 검증 완료로 확인된 근거만 — 미검증 근거는 건드리지 않는다)."""
    el = _els(db, card)[key]
    for ev in db.query(CardNewsEvidence).filter_by(card_id=card.id, element_key=key).all():
        if ev.original_footnote_status == "matched":
            ev.verification_status = "verified"
            ev.verified_text_hash = svc.text_hash(el.text, svc._load_json(el.data_json))
            ev.verified_by_user_id, ev.verified_at = reviewer.id, datetime.now(timezone.utc)


def _link(db, cn, card, key, footnote, user):
    svc.add_evidence_from_footnote(db, cn, card, key, footnote, user.id)


def _export_all(db, cn, user, out: Path, prefix: str):
    results = {}
    for fmt in ("pptx", "png"):
        exp = svc.generate_export(db, cn, file_format=fmt, user_id=user.id, short_px=1000)
        if exp.status != "success":
            raise SystemExit(f"{prefix} {fmt} 생성 실패: {exp.error_message}")
        results[fmt] = exp
    pptx = out / f"{prefix}.pptx"
    shutil.copy(results["pptx"].file_path, pptx)
    pngs = []
    with zipfile.ZipFile(results["png"].file_path) as zf:
        folder = out / f"{prefix}_png"
        folder.mkdir(parents=True, exist_ok=True)
        for n, name in enumerate(sorted(x for x in zf.namelist() if x.endswith(".png")), start=1):
            path = folder / f"card-{n:02d}.png"
            path.write_bytes(zf.read(name))
            pngs.append(path)
        for name in zf.namelist():
            if name.endswith("출처목록.txt"):
                (folder / "출처목록.txt").write_bytes(zf.read(name))
    v = json.loads(results["png"].validation_json)
    issues = [i for i in v["issues"] if i["level"] != "info"]
    print(f"  {prefix}: 카드 {len(pngs)}장, PPTX {results['pptx'].file_size}B, PNG {results['png'].png_width_px}×{results['png'].png_height_px}px, 점검 {len(issues)}건")
    for i in issues:
        print("     -", i["level"], i["code"], i["message"][:90])
    return pngs


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pilot_card_news")
    out.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        author = db.query(User).filter_by(email="dev-researcher-1@example.com").one()
        reviewer = db.query(User).filter_by(email="dev-reviewer-1@example.com").one()
        pilot = db.query(Manuscript).filter(Manuscript.title.like("[시범] 미국 NHTSA%")).first()
        report = db.query(Report).filter(Report.title.like("[시범] 주간 AI·ICT 동향 일반호%")).first()
        if pilot is None or report is None:
            raise SystemExit("먼저 python -m app.create_pilot_manuscript, python -m app.create_pilot_reports 를 실행하세요")
        _cleanup(db)
        fns = {fn.anchor_text[:12]: fn for fn in db.query(ManuscriptFootnote).filter_by(manuscript_id=pilot.id).all()}
        fn_by = lambda token: next(f for f in fns.values() if token in f.anchor_text)

        # ---------------- A형: 보고서 연계(FMVSS 305a) ----------------
        sentences = svc.source_sentences(db, report)
        pick = lambda token: next(s for s in sentences if token in s["sentence"])
        selections = [
            {"manuscript_id": pilot.id, "sentence": pick("공고함")["sentence"]},
            {"manuscript_id": pilot.id, "sentence": pick("동일 RIN")["sentence"]},
            {"manuscript_id": pilot.id, "sentence": pick("최종 규정은 2025.2.18.")["sentence"]},
            {"manuscript_id": pilot.id, "sentence": pick("총중량 4,536kg")["sentence"]},
        ]
        a = svc.create_card_news(
            db, user_id=author.id, title="[시범] 카드뉴스 A형 — FMVSS 305a 제정 동향", template_key="A", source_type="report",
            source_report_id=report.id, selections=selections, body_count=2, is_pilot=True,
        )
        cards = svc._cards(db, a)
        cover, b1, b2, closing = cards
        e = _els(db, cover)
        _set(e["title"], "미국 NHTSA 전기차 동력계 안전기준(FMVSS 305a) 제정 동향")
        _set(e["subtitle"], "제정안 공고부터 시행·준수 시한까지")
        _set(e["source"], "미국 NHTSA(연방관보)")
        e = _els(db, b1)
        _set(e["heading"], "추진 경과와 시행 일정")
        _set(e["content_1"], "2024.4.15. NHTSA가 FMVSS No. 305a 제정안(NPRM)을 공고함. 의견수렴 마감은 2024.6.14.임")
        _set(e["content_2"], "2024.12.20. 동일 RIN으로 최종 규정(Docket NHTSA-2024-0091)이 공고됨")
        _set(e["content_3"], "최종 규정은 2025.2.18.부터 시행되며, 비상대응정보 문서화 요건의 준수 시한은 2025.12.22.임")
        _set(e["implication"], "시행일과 준수 시한을 구분해 관리해야 함")
        _set(e["source"], "미국 NHTSA, 연방관보")
        _link(db, a, b1, "content_2", fn_by("최종 규정은 2025.2.18."), author)  # 같은 최종 규정 문서(연방관보)
        e = _els(db, b2)
        _set(e["heading"], "준수 시한과 추가 조사")
        _set(e["content_1"], "총중량 4,536kg 이하 차량의 그 밖의 요건 준수 시한은 2027.9.1.임")
        _set(e["content_2"], "중량 초과 차량의 시한은 별도 확인 후 보완 필요")
        _set(e["implication"], "국내 산업 영향은 원문에 근거가 없어 추가 조사 필요")
        _set(e["source"], "미국 NHTSA, 연방관보")
        e = _els(db, closing)
        _set(e["message"], "시행일(2025.2.18.)과 준수 시한(2025.12.22., 2027.9.1.)은 구분해서 확인해야 함")
        _set(e["follow_up"], "국내 산업 영향은 추가 조사 필요")
        _set(e["source"], "미국 NHTSA(연방관보)")
        _link(db, a, closing, "message", fn_by("최종 규정은 2025.2.18."), author)
        _link(db, a, closing, "message", fn_by("2027.9.1."), author)
        db.flush()
        # 카드에서의 검증: 원고 각주가 원문과 일치로 확인된 근거만 연구원이 검증 완료 처리(2027.9.1. 근거는 미검증 유지)
        _verify(db, a, b1, "content_1", reviewer)
        _verify(db, a, b1, "content_3", reviewer)
        svc.bump(a)
        svc.snapshot(db, a, author.id, note="시범 카드 내용 확정", milestone=True)
        db.commit()

        # ---------------- B형: 추진 일정(타임라인) ----------------
        b = svc.create_card_news(db, user_id=author.id, title="[시범] 카드뉴스 B형 — FMVSS 305a 추진 일정", template_key="B",
                                 body_count=1, is_pilot=True)
        cover, body, closing = svc._cards(db, b)
        e = _els(db, cover)
        _set(e["title"], "FMVSS 305a 추진 일정")
        _set(e["subtitle"], "제정안 공고 → 최종 규정 → 시행 → 준수 시한")
        _set(e["source"], "미국 NHTSA(연방관보)")
        e = _els(db, body)
        _set(e["heading"], "단계별 추진 일정")
        stages = [("announce", "2024.4.15.", "FMVSS No. 305a 제정안(NPRM) 공고", "FMVSS No. 305a 제정안"),
                  ("comment", "2024.6.14.", "제정안 의견수렴 마감", "의견수렴 마감은 2024.6.14."),
                  ("final", "2024.12.20.", "최종 규정 공고(Docket NHTSA-2024-0091)", None),
                  ("effective", "2025.2.18.", "최종 규정 시행", "최종 규정은 2025.2.18."),
                  ("compliance", "2025.12.22.", "비상대응정보 문서화 요건 준수 시한", "비상대응정보 문서화 요건")]
        for i, (kind, date, text, token) in enumerate(stages, start=1):
            _set(e[f"stage_{i}_kind"], kind)
            _set(e[f"stage_{i}_date"], date)
            _set(e[f"stage_{i}_text"], text)
            footnote = fn_by(token) if token else fn_by("최종 규정은 2025.2.18.")  # 최종 규정 공고는 같은 연방관보 문서
            for target in (f"stage_{i}_date", f"stage_{i}_text"):
                _link(db, b, body, target, footnote, author)
        _set(e["source"], "미국 NHTSA, 연방관보")
        e = _els(db, closing)
        _set(e["message"], "2027.9.1.까지 총중량 4,536kg 이하 차량의 준수 시한이 남아 있음")
        _set(e["follow_up"], "2027.9.1. 총중량 4,536kg 이하 차량 준수 시한(원고 근거 미검증 — 확인 필요)")
        _set(e["source"], "미국 NHTSA(연방관보)")
        _link(db, b, closing, "message", fn_by("2027.9.1."), author)
        db.flush()
        for i in range(1, 6):
            for target in (f"stage_{i}_date", f"stage_{i}_text"):
                _verify(db, b, body, target, reviewer)
        svc.bump(b)
        svc.snapshot(db, b, author.id, note="시범 카드 내용 확정", milestone=True)
        db.commit()

        # ---------------- C형: 주요국 비교(합성) ----------------
        c = svc.create_card_news(db, user_id=author.id, title=f"{SYN} 카드뉴스 C형 — 주요국 AI 규제 비교", template_key="C",
                                 body_count=1, is_pilot=True, is_synthetic=True)
        cover, body, closing = svc._cards(db, c)
        e = _els(db, cover)
        _set(e["badge"], "주요국 비교(합성)")
        _set(e["title"], f"{SYN} 주요국 AI 규제 접근 비교")
        _set(e["subtitle"], "합성 데이터로 만든 비교형 예시 — 실제 정책 아님")
        _set(e["source"], "합성 테스트 데이터")
        e = _els(db, body)
        _set(e["heading"], "국가별 정책 방향(합성)")
        _set(e["topic"], "AI 안전 규제 접근")
        _set(e["country_1_name"], "A국")
        _set(e["country_1_policy"], "사전 승인 중심의 위험기반 규제를 도입(합성)")
        _set(e["country_2_name"], "B국")
        _set(e["country_2_policy"], "자율규제와 사후 감독을 병행(합성)")
        _set(e["country_3_name"], "C국")  # C국 정책은 자료가 없어 비워 둔다 → '자료 부족 — 추가 조사 필요'로 표시
        _set(e["difference"], "승인 시점과 감독 강도가 다름(합성)")
        _set(e["common"], "고위험 AI의 정의 논의는 공통(합성)")
        _set(e["implication"], "국내 시사점은 추가 조사 필요")
        _set(e["source"], "합성 테스트 데이터")
        e = _els(db, closing)
        _set(e["message"], "국가별 규제 접근은 사전·사후로 구분됨(합성)")
        _set(e["follow_up"], "C국 자료 확보 및 국내 시사점 추가 조사 필요")
        _set(e["source"], "합성 테스트 데이터")
        db.flush()
        svc.bump(c)
        svc.snapshot(db, c, author.id, note="합성 데이터 구성", milestone=True)
        db.commit()

        # ---------------- D형: 핵심 수치(합성, 그래프 + 메시지 중심 전환) ----------------
        d = svc.create_card_news(db, user_id=author.id, title=f"{SYN} 카드뉴스 D형 — 핵심 수치 시각화", template_key="D",
                                 body_count=2, is_pilot=True, is_synthetic=True)
        cover, body, body2, closing = svc._cards(db, d)
        e = _els(db, cover)
        _set(e["badge"], "핵심 수치(합성)")
        _set(e["title"], f"{SYN} 전기차 안전기준 적용 차량 규모")
        _set(e["subtitle"], "합성 수치로 만든 시각화 예시 — 실제 통계 아님")
        _set(e["source"], "합성 테스트 데이터")
        e = _els(db, body)
        _set(e["heading"], "핵심 수치(합성)")
        _set(e["stat_value"], "38")
        _set(e["stat_unit"], "%")
        _set(e["stat_label"], "A국 적용 대상 차량 비중(합성)")
        _set(e["chart"], data={"title": "적용 대상 차량 비중", "unit": "%", "base_year": "2026", "comparison": "국가별", "source": "합성 테스트 데이터",
                               "synthetic": True, "series": [{"label": "A국", "value": 38}, {"label": "B국", "value": 24}, {"label": "C국", "value": 17}]})
        _set(e["meaning"], "적용 범위가 넓을수록 제조사의 대응 부담이 커짐(합성)")
        _set(e["message"], "수치는 합성 테스트용이며 실제 통계가 아님")
        _set(e["source"], "합성 테스트 데이터")
        e = _els(db, body2)
        _set(e["heading"], "통계가 없을 때")
        _set(e["meaning"], "검증된 수치가 없으면 억지로 그래프를 만들지 않고 메시지 중심 레이아웃으로 전환함")
        _set(e["message"], "검증된 수치가 확보된 뒤에만 그래프를 표시함")
        _set(e["source"], "합성 테스트 데이터")
        e = _els(db, closing)
        _set(e["message"], "검증된 수치만 그래프로 표시함(합성)")
        _set(e["follow_up"], "실제 통계 확보 후 산업 영향 추가 조사")
        _set(e["source"], "합성 테스트 데이터")
        db.flush()
        svc.bump(d)
        svc.snapshot(db, d, author.id, note="합성 데이터 구성", milestone=True)
        db.commit()

        print("시범 카드뉴스 출력 생성")
        for cn, prefix in ((a, "A_FMVSS305a_핵심요약"), (b, "B_FMVSS305a_추진일정"), (c, "C_주요국비교_합성"), (d, "D_핵심수치_합성")):
            db.refresh(cn)
            _export_all(db, cn, author, out, prefix)
        print("완료:", out.resolve())
    finally:
        db.close()


if __name__ == "__main__":
    main()
