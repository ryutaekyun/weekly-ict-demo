"""Phase 3-4 시범 업무 — 주간기술동향지 1회차의 의뢰→접수→검토→저자 수정→심의→교정→발간본 흐름(합성 데이터).

- 가상 집필진 2명·서로 다른 전문 분야 원고 2건. 인물·기관·원고는 모두 합성이며 실제 ICT 동향·실제 인물이 아니다.
- 실제 전문가에게 연락하거나 이메일을 보내지 않는다. 저자 계정의 비밀번호는 무작위로 만들고 출력하지 않는다(개발 DB 안에서만 쓰는 계정).
- API 라우트를 그대로 호출(권한 검사 포함)하되, 개발 DB의 더미 계정을 역할별로 바꿔 가며 사용한다.

실행: python -m app.create_pilot_journal [출력폴더]
      (개발 DB에 dev-researcher-1(편집)·dev-reviewer-1(검토)·dev-admin(관리자·승인권자) 더미 계정이 있어야 한다)
"""

import io
import json
import secrets
import sys
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

from app.core.db import SessionLocal, get_db
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.journal import JournalIssue
from app.models.user import User
from app.services import report_pdf

YEAR = 2027
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_docx(title: str, paras: list[str], table: list[list[str]] | None = None, table_title: str = "") -> bytes:
    d = Document()
    d.add_heading(title, level=1)
    d.add_heading("1. 배경", level=2)
    for p in paras[:3]:
        d.add_paragraph(p)
    d.add_heading("2. 주요 동향", level=2)
    for p in paras[3:]:
        d.add_paragraph(p)
    if table:
        d.add_paragraph(table_title)
        t = d.add_table(rows=len(table), cols=len(table[0]))
        t.style = "Table Grid"
        for r, row in enumerate(table):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    d.add_heading("참고문헌", level=2)
    d.add_paragraph("[1] 합성 참고문헌 1(실제 문헌이 아님).")
    d.add_paragraph("[2] 합성 참고문헌 2(실제 문헌이 아님).")
    d.core_properties.title = title
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pilot_journal")
    out.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    editor = db.query(User).filter_by(email="dev-researcher-1@example.com").one()
    reviewer = db.query(User).filter_by(email="dev-reviewer-1@example.com").one()
    admin = db.query(User).filter_by(email="dev-admin@example.com").one()
    if db.query(JournalIssue).filter_by(year=YEAR, issue_no=1, is_synthetic=True).first() and db.query(JournalIssue).filter_by(year=YEAR, status="published").first():
        raise SystemExit("시범 업무가 이미 실행되었습니다 — 중복 생성하지 않습니다.")

    authors = {}
    for key, name in (("a", "가상 연구자 가"), ("b", "가상 연구자 나")):
        email = f"dev-pilot-author-{key}@example.com"
        u = db.query(User).filter_by(email=email).one_or_none()
        if u is None:
            u = User(email=email, password_hash=hash_password(secrets.token_urlsafe(24)), display_name=name, role=UserRole.AUTHOR, job_title="외부 전문가(합성)")
            db.add(u)
            db.commit()
        authors[key] = u
    state = {"user": admin}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    def call(user: User, method: str, path: str, ok: tuple[int, ...] = (200, 201), **kw):
        state["user"] = user
        db.expire_all()
        r = client.request(method, path, **kw)
        if r.status_code not in ok:
            raise SystemExit(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    print("1) 2027년 25회 계획 등록(발간일은 관리자가 입력)")
    call(editor, "POST", "/journal/issues/plan-year", json={"year": YEAR, "count": 25, "is_synthetic": True})
    issue = next(i for i in call(editor, "GET", f"/journal/issues?year={YEAR}") if i["issue_no"] == 1)
    iid = issue["id"]
    call(admin, "PATCH", f"/journal/issues/{iid}", json={"publish_date": "2027-03-31", "topic": "[합성] 기술동향 시범 회차", "tech_field": "AI·반도체",
                                                         "editor_user_id": str(editor.id)})

    print("2) 가상 집필진 2명 등록·동의 기록·포털 계정 연결")
    experts = {}
    for key, name, aff, fields in (("a", "합성전문가 가(가상)", "가상대학교 인공지능연구소", ["AI", "데이터"]), ("b", "합성전문가 나(가상)", "가상반도체연구원", ["반도체", "ICT 융합"])):
        e = call(editor, "POST", "/journal/experts", json={"name": name, "affiliation": aff, "email": f"{key}.synthetic@example.com", "fields": fields, "is_synthetic": True,
                                                            "research_summary": "합성 연구 분야 소개(실제 인물이 아님)"})
        call(editor, "POST", f"/journal/experts/{e['id']}/consent", json={"consent_status": "agreed"})
        dbe = db.get(__import__("app.models.journal", fromlist=["JournalExpert"]).JournalExpert, __import__("uuid").UUID(e["id"]))
        dbe.user_id = authors[key].id
        db.commit()
        experts[key] = e
    dup = client.post("/journal/experts", json={"name": "합성전문가 가(가상)", "affiliation": "가상대학교 인공지능연구소"})
    print("   중복 등록 시도 →", dup.status_code, "(409면 정상)")

    print("3) 원고 의뢰서 작성·안내 메일 임시저장(발송 대기, 실제 발송 없음)·수락")
    subjects = {"a": "[합성] 생성형 AI 안전성 평가체계 동향", "b": "[합성] 첨단 패키징 공급망 동향"}
    coms = {}
    for key in ("a", "b"):
        c = call(editor, "POST", "/journal/commissions", json={"issue_id": iid, "expert_id": experts[key]["id"], "topic": subjects[key], "purpose": "합성 시범 의뢰",
                                                               "due_date": "2027-03-05", "length_spec": "(해당 연도 안내 기준 확인 후 입력)"})
        prev = call(editor, "GET", f"/journal/commissions/{c['id']}/mail-preview")
        call(editor, "PUT", f"/journal/commissions/{c['id']}/mail", json={"subject": prev["subject"], "body": prev["body"], "queue": True})
        call(editor, "POST", f"/journal/commissions/{c['id']}/status", json={"status": "requested"})
        call(authors[key], "POST", f"/journal/portal/author/commissions/{c['id']}/respond", json={"response": "accept", "note": "합성 수락"})
        coms[key] = c

    print("4) 저자 원고 제출(보안 검사·형식 점검) — 원고 A")
    paras_a = ["이 문서는 시범 업무 검증을 위한 합성 원고이며 실제 ICT 동향이 아닙니다.", "생성형 AI의 안전성 평가는 평가 항목 정의에서 출발한다고 가정합니다.",
               "국가별 평가체계는 사전 인증과 사후 점검으로 나뉜다고 가정한 합성 서술입니다.", "첫 번째 쟁점은 평가 기준의 객관성입니다(합성).",
               "두 번째 쟁점은 평가 결과의 공개 범위입니다(합성).", "세 번째 쟁점은 중소기업의 평가 부담입니다(합성)."]
    paras_b = ["이 문서는 시범 업무 검증을 위한 합성 원고이며 실제 ICT 동향이 아닙니다.", "첨단 패키징은 공급망의 병목 지점으로 가정한 합성 서술입니다.",
               "장비·소재·후공정 기업의 역할을 단순화해 설명합니다(합성).", "첫 번째 동향은 후공정 투자 확대입니다(합성).", "두 번째 동향은 소재 다변화입니다(합성)."]
    table_a = [["구분", "A국(합성)", "B국(합성)"], ["평가 방식", "사전 인증", "사후 점검"], ["공개 범위", "요약 공개", "전체 공개"]]
    files = {"a": make_docx(subjects["a"], paras_a, table_a, "[표 1] 합성 평가체계 비교"), "b": make_docx(subjects["b"], paras_b)}
    ms_ids = {}
    for key in ("a", "b"):
        state["user"] = authors[key]
        db.expire_all()
        resp = client.post(f"/journal/portal/author/commissions/{coms[key]['id']}/submit", files={"file": (f"{key}_원고.docx", files[key], DOCX)}, data={
            "title": subjects[key], "title_en": "Synthetic Manuscript", "summary": "합성 요약", "authors_json": json.dumps([{"name": experts[key]["name"], "affiliation": experts[key]["affiliation"], "corresponding": True}]),
            "references_text": "[1] 합성", "copyright_confirmed": "true", "third_party_note": "제3자 자료 없음(합성)"})
        assert resp.status_code == 201, resp.text
        ms_ids[key] = resp.json()["id"]
        call(editor, "POST", f"/journal/manuscripts/{ms_ids[key]}/format-review", json={"result": "ok"})

    print("5) 원고 A: 1차 검토 → 수정 요청 → 저자 수정 → 버전 비교 → 2차 검토 → 심의 → 게재 확정")
    a = ms_ids["a"]
    asg = call(editor, "POST", f"/journal/manuscripts/{a}/assignments", json={"reviewer_user_id": str(reviewer.id), "due_date": "2027-02-20"})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg['id']}/conflict", json={"declared": False})
    c1 = call(reviewer, "POST", f"/journal/portal/reviews/{asg['id']}/comments", json={"scope": "paragraph", "anchor_text": paras_a[3], "text": "평가 기준의 객관성에 대한 근거 문장을 보강해 주세요."})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg['id']}/comments", json={"scope": "table", "anchor_text": "[표 1] 합성 평가체계 비교", "text": "표의 비교 항목 정의를 본문에 설명해 주세요."})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg['id']}/comments", json={"scope": "doc", "text": "결론 문단이 없습니다. 시사점을 정리해 주세요."})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg['id']}/complete", json={"recommendation": "major", "summary_opinion": "주요 수정 후 재검토 필요(합성 의견)"})
    call(editor, "POST", f"/journal/manuscripts/{a}/request-revision", json={})
    detail = call(authors["a"], "GET", f"/journal/portal/author/manuscripts/{a}")
    for cm in detail["comments"]:
        call(authors["a"], "POST", f"/journal/portal/author/manuscripts/{a}/comments/{cm['id']}/reply", json={"text": "해당 부분을 보강했습니다(합성 답변)."})
    paras_a2 = [paras_a[0], paras_a[1], paras_a[2], "평가 기준의 객관성은 정량 지표와 전문가 판단을 병행해 확보한다고 보강했습니다(합성).", paras_a[4], paras_a[5],
                "결론: 평가체계는 단계적으로 도입하는 방안이 논의됩니다(합성 시사점)."]
    state["user"] = authors["a"]
    db.expire_all()
    rv = client.post(f"/journal/portal/author/manuscripts/{a}/revision", files={"file": ("a_수정본.docx", make_docx(subjects["a"], paras_a2, table_a, "[표 1] 합성 평가체계 비교"), DOCX)}, data={"note": "의견 반영"})
    assert rv.status_code == 201, rv.text
    cmp = call(editor, "GET", f"/journal/manuscripts/{a}/compare?from=1&to=2")
    (out / "원고A_버전비교.json").write_text(json.dumps(cmp, ensure_ascii=False, indent=2), encoding="utf-8")
    print("   버전 비교:", cmp["counts"], "| 원본 비교 필요:", cmp["needs_original_compare"], cmp["original_compare_reasons"])
    asg2 = call(editor, "POST", f"/journal/manuscripts/{a}/assignments", json={"reviewer_user_id": str(reviewer.id), "round": 2})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg2['id']}/conflict", json={"declared": False})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg2['id']}/complete", json={"recommendation": "accept", "summary_opinion": "수정 확인(합성 의견)"})
    for cm in call(editor, "GET", f"/journal/manuscripts/{a}")["comments"]:
        call(editor, "POST", f"/journal/manuscripts/{a}/comments/{cm['id']}/resolve")
    call(editor, "POST", f"/journal/manuscripts/{a}/deliberate")
    call(admin, "POST", f"/journal/manuscripts/{a}/decision", json={"outcome": "accept", "note": "게재 확정(합성 시범)"})

    print("6) 원고 B: 1차 검토 후 바로 심의 → 게재 확정(권한이 없는 편집자의 확정 시도는 거부)")
    b = ms_ids["b"]
    asg_b = call(editor, "POST", f"/journal/manuscripts/{b}/assignments", json={"reviewer_user_id": str(reviewer.id)})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg_b['id']}/conflict", json={"declared": False})
    call(reviewer, "POST", f"/journal/portal/reviews/{asg_b['id']}/complete", json={"recommendation": "accept", "summary_opinion": "적합(합성 의견)"})
    call(editor, "POST", f"/journal/manuscripts/{b}/deliberate")
    state["user"] = editor
    r403 = client.post(f"/journal/manuscripts/{b}/decision", json={"outcome": "accept"})
    print("   편집자의 게재 확정 시도 →", r403.status_code, "(403이면 정상)")
    call(admin, "POST", f"/journal/manuscripts/{b}/decision", json={"outcome": "accept", "note": "게재 확정(합성 시범)"})

    print("7) 교정본 업로드·최종 교정 확인 → 회차 구성 → 발간본 출력")
    checklist = {k: True for k in ("source", "figure_table_numbers", "references", "abbreviations", "language")}
    for key, mid, content in (("a", a, make_docx(subjects["a"], paras_a2, table_a, "[표 1] 합성 평가체계 비교")), ("b", b, files["b"])):
        state["user"] = editor
        db.expire_all()
        up = client.post(f"/journal/manuscripts/{mid}/versions", files={"file": (f"{key}_교정본.docx", content, DOCX)}, data={"kind": "proofread"})
        assert up.status_code == 201, up.text
        call(editor, "POST", f"/journal/manuscripts/{mid}/proof/confirm", json={"checklist": checklist})
    call(editor, "PUT", f"/journal/issues/{iid}/items", json={"manuscript_ids": [a, b]})
    detail = call(editor, "GET", f"/journal/issues/{iid}")
    print("   발간 점검:", [(p["level"], p["code"]) for p in detail["export_preflight"]])
    results = {}
    for fmt in ("docx", "pdf"):
        exp = call(admin, "POST", f"/journal/issues/{iid}/exports", json={"file_format": fmt, "final": True})
        assert exp["status"] == "success", exp["error_message"]
        content = call(admin, "GET", f"/journal/issues/{iid}/exports/{exp['id']}/download", ok=(200,))
        (out / f"기술동향지_{YEAR}_1호_확정.{fmt}").write_bytes(content.content)
        results[fmt] = exp
        print(f"   {fmt}: {exp['file_size']}B, 페이지 {exp['page_count']}, 템플릿 v{exp['template_version']}, 원고 버전 {[i['version_no'] for i in exp['items']]}")
    pdf_bytes = (out / f"기술동향지_{YEAR}_1호_확정.pdf").read_bytes()
    report_pdf.render_pages_png(pdf_bytes, out / "발간본_pages")
    call(admin, "POST", f"/journal/issues/{iid}/publish")
    print("   발간 이력 기록(IITP 확인은 별도 — 현재", call(editor, "GET", f"/journal/issues/{iid}")["iitp_confirmed"], ")")

    summary = call(admin, "GET", f"/journal/dashboard?year={YEAR}")
    (out / "대시보드_요약.json").write_text(json.dumps({k: summary[k] for k in ("plan", "commission_status", "manuscript_status", "review")}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("완료:", out.resolve())
    app.dependency_overrides.clear()
    db.close()


if __name__ == "__main__":
    main()
