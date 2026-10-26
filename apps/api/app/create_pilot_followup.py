"""Phase 3-3.1 — FMVSS 305a 후속 규정 반영 흐름(시범).

연방관보 공식 API에서 후속 문서를 직접 확인하고(네트워크), 다음 흐름을 실제 데이터로 수행한다.
  후속 규정 등록 → 영향받는 원고·보고서·카드뉴스에 '재검토 필요' 표시 → 검토자 수정 요청 → 연구원이 원고 수정(새 버전)
  → 원고 문장이 바뀐 카드뉴스를 연구원이 직접 수정하고 근거 재검증 → 연구원 확인(ack) → 새 버전 출력

원칙: 기존 원고 버전·기존 출력본·카드뉴스 이전 버전은 지우지 않는다. 검증은 발췌문이 공식 원문(연방관보 본문)에 그대로
있을 때만 검토자가 처리하고, 2027.9.1. 준수 시한 근거는 이전처럼 미검증으로 남긴다.

실행: python -m app.create_pilot_followup [카드뉴스 출력폴더] [보고서 출력폴더]
      (먼저 create_pilot_manuscript → create_pilot_reports → create_pilot_card_news 실행)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.db import SessionLocal
from app.create_pilot_card_news import SYN, _els, _export_all, _link, _set, _verify
from app.create_pilot_manuscript import _heading, _para, _plain, _text
from app.create_pilot_reports import _add, _export_both, _new_report
from app.models.card_news import CardNews, CardNewsEvidence
from app.models.document_full_text import DocumentFullText
from app.models.enums import EvidenceMatchStatus
from app.models.followup import FollowupAck, FollowupNotice
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.report import Report
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services import card_news_service as svc
from app.services import followup_service, manuscript_comment_service, manuscript_footnote_service, manuscript_service

ORG = "미국 국가도로교통안전청(NHTSA)"
FR_TEXT_URL = "https://www.federalregister.gov/documents/full_text/text/2025/02/14/2025-02582.txt"


def _norm(s: str) -> str:
    """공백 정리 + PDF 줄바꿈 하이픈 흔적('Small- volume')을 이어 붙여 비교한다."""
    import re
    return re.sub(r"(\w)- (\w)", lambda m: f"{m.group(1)}-{m.group(2)}", " ".join(s.split()))


def _set_verified(fn: ManuscriptFootnote, reviewer: User, full_text: str, excerpt: str) -> bool:
    """발췌문이 공식 원문에 그대로 있을 때만 검토자가 '원문과 일치'로 처리한다."""
    if _norm(excerpt) in _norm(full_text):
        fn.verification_status = EvidenceMatchStatus.MATCHED
        fn.verified_by_user_id, fn.verified_at = reviewer.id, datetime.now(timezone.utc)
        return True
    return False


def _swap_first(nodes: list, text_prefix: str, replacement: list) -> list:
    out = []
    done = False
    for n in nodes:
        if not done and n.get("type") == "text" and n["text"].startswith(text_prefix):
            out.extend(replacement)
            done = True
        else:
            out.append(n)
    assert done, text_prefix
    return out


def main() -> None:
    out_cards = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pilot_card_news_331")
    out_reports = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("pilot_outputs_331")
    out_cards.mkdir(parents=True, exist_ok=True)
    out_reports.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        author = db.query(User).filter_by(email="dev-researcher-1@example.com").one()
        reviewer = db.query(User).filter_by(email="dev-reviewer-1@example.com").one()
        approver = db.query(User).filter_by(email="dev-admin@example.com").one()
        ms = db.query(Manuscript).filter(Manuscript.title.like("[시범] 미국 NHTSA%")).one()
        if db.query(FollowupNotice).filter_by(followup_doc_number="2025-02582").first():
            raise SystemExit("후속 규정 흐름이 이미 실행되었습니다 — 시범 DB를 재구성한 뒤 다시 실행하세요.")

        # ---- 1. 공식 원문 확인(연방관보 API·본문) ----
        meta1 = followup_service.fetch_federal_register("2025-02582")
        meta2 = followup_service.fetch_federal_register("2026-11072")
        delay_text = httpx.get(FR_TEXT_URL, timeout=30, follow_redirects=True).text
        print("후속 규정 1:", meta1["document_number"], meta1["publication_date"], "시행일", meta1["effective_on"])
        print("후속 규정 2:", meta2["document_number"], meta2["publication_date"], "시행일", meta2["effective_on"], "(305a 조문 참조 정정)")
        if meta1["effective_on"] != "2025-03-20":
            raise SystemExit("공식 API의 시행일이 예상과 다릅니다 — 중단")

        fn_eff = db.query(ManuscriptFootnote).filter(ManuscriptFootnote.manuscript_id == ms.id,
                                                      ManuscriptFootnote.anchor_text.like("최종 규정은 2025.2.18.%")).one()
        final_doc = db.get(SourceDocument, fn_eff.source_document_id)
        final_full = db.query(DocumentFullText).filter_by(document_id=final_doc.id).one().full_text or ""

        # ---- 2. 후속 규정 등록 → 영향 확인 ----
        n1 = FollowupNotice(
            title="FMVSS No. 305a 최종 규정 시행일 연기(2025.2.18. → 2025.3.20.)", original_doc_number="2024-28707",
            original_url=final_doc.origin_url, followup_doc_number="2025-02582", followup_url=meta1["html_url"], followup_org=ORG,
            followup_published_at=followup_service.parse_dt(meta1["publication_date"]), followup_effective_on=meta1["effective_on"],
            change_summary="2024.12.20. 최종 규정의 시행일을 2025.3.20.으로 연기함. 준수 시한은 이 문서에서 바뀌지 않음.",
            changes_json=json.dumps([{"item": "시행일", "old": "2025.2.18.", "new": "2025.3.20."}], ensure_ascii=False),
            is_pilot=True, created_by_user_id=author.id)
        n2 = FollowupNotice(
            title="FMVSS No. 214 개정에 따른 305a 조문 참조 정정(날짜 변경 없음)", original_doc_number="2024-28707",
            original_url=final_doc.origin_url, followup_doc_number="2026-11072", followup_url=meta2["html_url"], followup_org=ORG,
            followup_published_at=followup_service.parse_dt(meta2["publication_date"]), followup_effective_on=meta2["effective_on"],
            change_summary="FMVSS 214의 폐지된 조항을 가리키던 305a S9.3의 참조를 정정하는 형식적 개정. 시행일·준수 시한 변경 없음(연구원 확인 필요).",
            changes_json="[]", is_pilot=True, created_by_user_id=author.id)
        db.add_all([n1, n2])
        db.flush()
        impact = followup_service.impact_summary(db, n1)
        print("영향 산출물(알림 1):", {k: len(v) for k, v in impact.items()})
        a = db.query(CardNews).filter(CardNews.title.like("[시범] 카드뉴스 A형%")).one()
        b = db.query(CardNews).filter(CardNews.title.like("[시범] 카드뉴스 B형%")).one()
        before = [i["code"] for i in svc.run_preflight(db, a) if i["code"] == "followup_pending"]
        print("A형 카드뉴스 사전점검(후속 규정 등록 직후): followup_pending", len(before), "건 → 확정 차단")
        db.commit()

        # ---- 3. 원고 수정(검토자 수정 요청 → 연구원 수정, 새 버전) ----
        manuscript_service.request_changes(db, ms)
        comment = manuscript_comment_service.create_comment(
            db, manuscript_id=ms.id, author_user_id=reviewer.id, anchor_text="최종 규정은 2025.2.18.부터 시행됨",
            comment_text="후속 규정(2025-02582)으로 시행일이 2025.3.20.으로 연기되었습니다. 시행일을 정정하고, 총중량 4,536kg 초과 차량의 준수 시한(2028.9.1.)도 원문 근거와 함께 보완해주세요.")
        fn_new = {}
        spec = {
            "followup_delay": ("2025.2.14. 공고된 후속 규정으로 시행일이 2025.3.20.으로 연기됨", meta1["html_url"], ORG,
                              "delays until March 20, 2025, the effective date of the December 20, 2024, final rule", delay_text,
                              followup_service.parse_dt(meta1["publication_date"]), None),
            "final_heavy": ("총중량 4,536kg 초과 차량의 그 밖의 요건 준수 시한은 2028.9.1.임", final_doc.origin_url, ORG,
                           "September 1, 2028, for vehicles with a gross vehicle weight rating over 4,536 kg", final_full, final_doc.published_at, final_doc.id),
            "final_extra": ("소량생산업체·최종단계 제조업체·개조업체에는 위 시한에 더해 1년의 추가 유예가 부여됨", final_doc.origin_url, ORG,
                           "Small-volume manufacturers, final-stage manufacturers, and alterers are provided an additional year to comply",
                           final_full, final_doc.published_at, final_doc.id),
        }
        import uuid
        mark = {k: str(uuid.uuid4()) for k in spec}
        for k, (anchor, url, org, excerpt, full, published, doc_id) in spec.items():
            fn = manuscript_footnote_service.create_footnote(
                db, manuscript_id=ms.id, created_by_user_id=author.id, mark_id=mark[k], anchor_text=anchor, source_url=url,
                source_document_id=doc_id, source_org=org, excerpt=excerpt, location_label=None, published_at=published)
            ok = _set_verified(fn, reviewer, full, excerpt)
            fn_new[k] = fn
            print(f"  새 각주 {k}: 공식 원문 대조 {'일치 → 검증' if ok else '불일치 → 미검증 유지'}")
        fn_eff.anchor_text = "최종 규정은 당초 2025.2.18.부터 시행될 예정이었음"

        doc = json.loads(ms.body_json)
        body = doc["content"]
        for node in body:
            if node.get("type") != "paragraph":
                continue
            texts = node["content"]
            first = texts[0].get("text", "") if texts else ""
            if first.startswith("최종 규정은 2025.2.18."):
                node["content"] = _swap_first(texts, "최종 규정은 2025.2.18.", [
                    _text(fn_eff.anchor_text, fn_eff.mark_id), _text(". "), _text(spec["followup_delay"][0], mark["followup_delay"])])
            elif first.startswith("총중량 4,536kg 이하"):
                node["content"] = [texts[0], _text(". "), _text(spec["final_heavy"][0], mark["final_heavy"]), _text(". "),
                                   _text(spec["final_extra"][0], mark["final_extra"]), _text(".")]
            elif first.startswith("※ 날짜 구분"):
                node["content"] = [_text("※ 날짜 구분: 의견수렴 마감(2024.6.14.) → 최종 규정 공고(2024.12.20.) → 시행일(2025.3.20., 당초 2025.2.18.에서 연기) → 준수 시한(2025.12.22. / 2027.9.1. / 2028.9.1.)임.")]
        manuscript_service.update_manuscript_body(
            db, ms, title=None, title_en=None, body_json=json.dumps(doc, ensure_ascii=False), body=_plain(doc),
            lock_version=ms.lock_version, actor_user_id=author.id,
            change_note="후속 규정(2025-02582) 반영 — 시행일 2025.3.20., 2028.9.1. 준수 시한·추가 유예 보완", is_milestone=True)
        manuscript_comment_service.resolve_comment(db, comment, resolver_user_id=author.id)
        manuscript_service.request_review(db, ms, reviewer_user_id=reviewer.id)
        db.commit()
        sentence = {k: spec[k][0] for k in spec}
        delay_sentence = fn_eff.anchor_text + ". " + spec["followup_delay"][0]

        # ---- 4. 카드뉴스 A형 수정(연구원이 직접) ----
        cover, b1, b2, closing = svc._cards(db, a)
        e = _els(db, b1)
        _set(e["content_3"], delay_sentence)
        e["content_3"].source_sentence = delay_sentence
        e["content_3"].source_manuscript_id = ms.id
        _link(db, a, b1, "content_3", fn_new["followup_delay"], author)
        _link(db, a, b1, "content_3", fn_eff, author)
        e = _els(db, b2)
        fn_light = next(f for f in db.query(ManuscriptFootnote).filter_by(manuscript_id=ms.id).all() if "4,536kg 이하" in f.anchor_text)
        fn_emerg = next(f for f in db.query(ManuscriptFootnote).filter_by(manuscript_id=ms.id).all() if "비상대응정보" in f.anchor_text)
        for ev in db.query(CardNewsEvidence).filter_by(card_id=b2.id).all():  # 항목 순서를 날짜순으로 재구성하므로 근거도 새로 연결한다
            db.delete(ev)
        db.flush()
        _set(e["heading"], "준수 시한(차량 구분별)")
        light_sentence = "총중량 4,536kg 이하 차량의 그 밖의 요건 준수 시한은 2027.9.1.임"
        emerg_sentence = "비상대응정보 문서화 요건의 준수 시한은 2025.12.22.임"
        rows = [
            ("content_1", emerg_sentence, emerg_sentence, [fn_emerg]),
            ("content_2", light_sentence, light_sentence, [fn_light]),
            ("content_3", sentence["final_heavy"] + "(소량생산업체 등은 1년 추가 유예)", sentence["final_heavy"],
             [fn_new["final_heavy"], fn_new["final_extra"]]),
        ]
        for key, text, src, fns in rows:
            _set(e[key], text)
            e[key].source_sentence, e[key].source_manuscript_id = src, ms.id
            for fn in fns:
                _link(db, a, b2, key, fn, author)
        db.flush()
        e = _els(db, closing)
        _set(e["message"], "시행일(2025.3.20.)과 준수 시한은 구분해서 확인해야 함")
        _set(e["follow_up"], "국내 산업 영향은 원문에 근거가 없어 추가 조사 필요")
        _link(db, a, closing, "message", fn_new["followup_delay"], author)
        db.flush()
        # 비상대응정보 준수 시한(2025.12.22.)은 첫 카드에서 빠졌으므로 둘째 카드 첫 항목 앞에 두지 않고 마무리 문구에 포함했다.
        for card, key in ((b1, "content_1"), (b1, "content_3"), (b2, "content_1"), (b2, "content_3"), (closing, "message")):
            _verify(db, a, card, key, reviewer)
        a.source_versions_json = json.dumps({str(ms.id): ms.lock_version})
        svc.bump(a)
        svc.snapshot(db, a, author.id, note="후속 규정(2025-02582) 반영 — 시행일 정정·2028.9.1. 보완", milestone=True)

        # ---- 5. 카드뉴스 B형 수정 ----
        cover, body_card, closing = svc._cards(db, b)
        e = _els(db, body_card)
        stages = [("announce", "2024.4.15.", "FMVSS No. 305a 제정안(NPRM) 공고", None),
                  ("final", "2024.12.20.", "최종 규정 공고(Docket NHTSA-2024-0091)", fn_eff),
                  ("changed", "2025.2.14.", "시행일 연기 규정 공고(2025-02582)", fn_new["followup_delay"]),
                  ("effective", "2025.3.20.", "최종 규정 시행(당초 2025.2.18.에서 연기)", fn_new["followup_delay"]),
                  ("compliance", "2025.12.22.", "비상대응정보 문서화 요건 준수 시한", None)]
        # 기존 근거 연결(제정안·준수 시한)은 단계 위치가 바뀌므로 근거 행의 element_key를 새 위치에 맞춰 옮긴다
        old_ev = db.query(CardNewsEvidence).filter_by(card_id=body_card.id).all()
        by_old = {}
        for ev in old_ev:
            by_old.setdefault(ev.element_key, []).append(ev)
        for ev in old_ev:
            db.delete(ev)
        db.flush()
        footnotes_by_token = {f.anchor_text[:10]: f for f in db.query(ManuscriptFootnote).filter_by(manuscript_id=ms.id).all()}
        nprm_fn = next(f for f in footnotes_by_token.values() if "제정안" in f.anchor_text)
        emerg_fn = next(f for f in footnotes_by_token.values() if "비상대응정보" in f.anchor_text)
        stage_fn = {1: nprm_fn, 2: fn_eff, 3: fn_new["followup_delay"], 4: fn_new["followup_delay"], 5: emerg_fn}
        for i, (kind, date, text, _fn) in enumerate(stages, start=1):
            _set(e[f"stage_{i}_kind"], kind)
            _set(e[f"stage_{i}_date"], date)
            _set(e[f"stage_{i}_text"], text)
            for target in (f"stage_{i}_date", f"stage_{i}_text"):
                _link(db, b, body_card, target, stage_fn[i], author)
        db.flush()
        e = _els(db, closing)
        _set(e["message"], "시행일(2025.3.20.)과 준수 시한을 구분해 확인해야 함")
        _set(e["follow_up"], "준수 시한: 2025.12.22.(비상대응정보), 2027.9.1.(4,536kg 이하), 2028.9.1.(초과)")
        _link(db, b, closing, "message", fn_new["followup_delay"], author)
        _link(db, b, closing, "follow_up", fn_new["final_heavy"], author)
        db.flush()
        for i in range(1, 6):
            for target in (f"stage_{i}_date", f"stage_{i}_text"):
                _verify(db, b, body_card, target, reviewer)
        _verify(db, b, closing, "message", reviewer)
        svc.bump(b)
        svc.snapshot(db, b, author.id, note="후속 규정(2025-02582) 반영 — 시행일 정정", milestone=True)
        db.commit()

        # ---- 6. 후속 반영 보고서 새로 출력(기존 보고서·출력본은 이력으로 유지) ----
        general = _new_report(db, author, "general", "[시범] 주간 AI·ICT 동향 일반호(후속 규정 반영) — 개발용 출력 테스트",
                              "[Pilot] Weekly AI·ICT Trends (follow-up rule reflected) — Output Test")
        _add(db, general, "key_issue", ms)
        db.commit()
        print("보고서 출력(후속 규정 반영본)")
        _export_both(db, general, author, out_reports, "01_일반호_후속규정반영")

        # ---- 7. 연구원 확인(ack) 기록 ----
        old_reports = db.query(Report).filter(Report.title.like("[시범] 주간 AI·ICT 동향%"), Report.id != general.id).all()
        targets = {"manuscript": [ms.id], "report": [r.id for r in old_reports] + [general.id], "card_news": [a.id, b.id]}
        for notice in (n1, n2):
            aff = followup_service.affected_entities(db, notice)
            for etype, ids in targets.items():
                for eid in ids:
                    if eid not in aff[etype]:
                        continue
                    if notice is n1:
                        resolution = "updated"
                        note = {"manuscript": "원고 새 버전에 시행일 정정(2025.3.20.)과 2028.9.1. 준수 시한을 반영함",
                                "report": "후속 반영 원고로 보고서를 새로 구성함(기존 보고서·출력본은 이력으로 유지)" if eid == general.id
                                else "후속 규정 반영 전 보고서 — 이력 보존용이며 후속 반영본 보고서를 새로 생성함",
                                "card_news": "카드 내용을 연구원이 직접 수정하고 근거를 다시 검증함"}[etype]
                    else:
                        resolution, note = "no_change", "연방관보 원문 확인 — 214 참조 정정뿐이며 이 산출물의 날짜·준수 시한에는 영향 없음"
                    db.add(FollowupAck(notice_id=notice.id, entity_type=etype, entity_id=eid, resolution=resolution, note=note,
                                       acked_by_user_id=author.id))
        db.commit()
        left = {t: len(followup_service.open_notices_for(db, t, ids[0])) for t, ids in targets.items()}
        print("확인 후 남은 후속 규정 알림(대상별):", left)

        # ---- 8. 카드뉴스 4종 재출력 ----
        print("카드뉴스 출력")
        c = db.query(CardNews).filter(CardNews.title.like(f"{SYN} 카드뉴스 C형%")).one()
        d = db.query(CardNews).filter(CardNews.title.like(f"{SYN} 카드뉴스 D형%")).one()
        for cn, prefix in ((a, "A_FMVSS305a_핵심요약"), (b, "B_FMVSS305a_추진일정"), (c, "C_주요국비교_합성"), (d, "D_핵심수치_합성")):
            db.refresh(cn)
            _export_all(db, cn, author, out_cards, prefix)
        print("완료:", out_cards.resolve(), out_reports.resolve())
    finally:
        db.close()


if __name__ == "__main__":
    main()
