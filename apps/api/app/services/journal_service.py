"""주간기술동향지 업무 로직 — 설정, 편집 일정, 의뢰·접수·검토·심의 상태 전이, 대시보드, 발간본 출력.

원칙
- 날짜·분량·제출서류·표절률 기준은 해당 연도 IITP 공식 기준이 확인되기 전까지 하드코딩하지 않고 관리자 설정으로 둔다(미설정이면 '기준 미설정').
- 기한이 지나도 단계를 자동으로 완료 처리하지 않는다(지연 표시). 자동 점수로 게재 여부를 정하지 않는다.
- 외부 이메일 발송·IITP 업로드는 하지 않는다(발송 대기 상태와 이력 구조만 둔다).
"""

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.journal import (
    JournalAssignment, JournalAttachment, JournalCommission, JournalCommissionEvent, JournalComment, JournalDecision, JournalExpert,
    JournalExport, JournalIssue, JournalIssueItem, JournalManuscript, JournalPlagiarism, JournalScheduleStep, JournalSetting, JournalVersion,
)
from app.models.user import User
from app.services import journal_docx, journal_files, report_docx, report_pdf

EDITOR_ROLES = (UserRole.RESEARCHER, UserRole.APPROVER, UserRole.ADMIN)
DECIDER_ROLES = (UserRole.APPROVER, UserRole.ADMIN)

# ---------------------------------------------------------------- 설정 ----
DEFAULT_STEPS = [
    {"key": "plan", "label": "주제 기획·집필진 후보 확보·원고 의뢰", "offset_days": 50, "window_start_days": 60},
    {"key": "receive", "label": "원고 접수 및 형식 확인", "offset_days": 25},
    {"key": "assign", "label": "편집 방향 부합성·유사도 확인 및 검토자 배정", "offset_days": 22},
    {"key": "review1", "label": "1차 원고 검토", "offset_days": 20},
    {"key": "revision", "label": "저자 수정 원고 접수", "offset_days": 15},
    {"key": "review2", "label": "2차 검토·원고 심의", "offset_days": 10},
    {"key": "editing", "label": "편집·교정·최종 원고 구성", "offset_days": 7},
    {"key": "iitp_check", "label": "IITP 최종 확인", "offset_days": 3},
    {"key": "publish", "label": "발간", "offset_days": 0},
]
DEFAULT_OUTCOMES = [
    {"key": "accept", "label": "게재 적합", "effect": "accept"},
    {"key": "minor", "label": "경미한 수정 후 게재", "effect": "revise"},
    {"key": "major", "label": "주요 수정 후 재검토", "effect": "revise"},
    {"key": "hold", "label": "게재 보류", "effect": "hold"},
    {"key": "reject", "label": "게재 부적합", "effect": "reject"},
]
DEFAULT_SETTINGS = {
    "day_basis": "calendar",  # calendar / business — D-n의 계산 기준
    "holiday_rule": "prev",  # none / prev / next — 휴일·주말에 걸린 마감일 조정(달력일 기준일 때)
    "holidays": [],  # ISO 날짜 목록(관리자가 입력)
    "schedule_steps": DEFAULT_STEPS,
    "max_upload_mb": 20,
    "manuscript_ext": ["docx", "pdf"],
    "attachment_ext": ["docx", "pdf", "png", "jpg", "jpeg", "xlsx", "txt"],
    "word_min": None,  # 분량 기준은 해당 연도 모집 안내 확인 후 관리자가 설정
    "word_max": None,
    "required_docs": [],  # [{"key","label"}] — 공식 양식·제출 기준 확인 후 설정
    "decision_outcomes": DEFAULT_OUTCOMES,
    "major_change_ratio": 0.3,  # 수정본에서 바뀐 문단 비율이 이 값을 넘으면 기존 검토의 유효성을 재검토
    "retention_months": None,  # 개인정보 보존 기간(미설정이면 보존 만료일 자동 계산 안 함)
    "due_soon_days": 3,
}
STATUS_LABELS = {
    "received": "접수 완료", "format_fix_needed": "형식 보완 필요", "review_pending": "내용 검토 대기", "in_review": "검토 진행 중",
    "revision_requested": "수정 요청", "revision_received": "수정본 접수", "deliberated": "심의 완료", "accepted": "게재 확정",
    "held": "게재 보류", "rejected": "게재 부적합·반려",
}
TRANSITIONS = {
    "received": {"format_fix_needed", "review_pending"},
    "format_fix_needed": {"received"},
    "review_pending": {"in_review", "format_fix_needed"},
    "in_review": {"revision_requested", "deliberated"},
    "revision_requested": {"revision_received"},
    "revision_received": {"in_review", "deliberated"},
    "deliberated": {"accepted", "held", "rejected", "revision_requested"},
    "held": {"review_pending", "rejected"},
    "accepted": set(),
    "rejected": set(),
}
COMMISSION_STATUS_LABELS = {"draft": "작성 중", "ready": "발송 대기", "requested": "의뢰함(응답 대기)", "accepted": "수락", "declined": "거절",
                            "no_response": "미응답"}
COMMISSION_TRANSITIONS = {
    "draft": {"ready", "requested"}, "ready": {"draft", "requested"}, "requested": {"accepted", "declined", "no_response"},
    "no_response": {"accepted", "declined", "requested"}, "accepted": {"declined"}, "declined": {"requested"},
}
ISSUE_STATUSES = ["planning", "recruiting", "receiving", "reviewing", "editing", "iitp_check", "published"]
ISSUE_STATUS_LABELS = {"planning": "기획", "recruiting": "집필진 확보", "receiving": "원고 접수", "reviewing": "검토·심의", "editing": "편집·교정",
                       "iitp_check": "IITP 확인 대기", "published": "발간 기록"}


def today() -> date:
    return date.today()


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_settings(db: Session) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_SETTINGS))
    for row in db.scalars(select(JournalSetting)).all():
        if row.key in cfg:
            try:
                cfg[row.key] = json.loads(row.value_json)
            except ValueError:
                pass
    return cfg


def set_settings(db: Session, patch: dict, user_id: uuid.UUID) -> dict:
    for key, value in patch.items():
        if key not in DEFAULT_SETTINGS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"알 수 없는 설정입니다: {key}")
        row = db.scalar(select(JournalSetting).where(JournalSetting.key == key))
        if row is None:
            row = JournalSetting(key=key, value_json="null")
            db.add(row)
        row.value_json = json.dumps(value, ensure_ascii=False)
        row.updated_by_user_id = user_id
    db.flush()
    return get_settings(db)


# ---------------------------------------------------------------- 일정 ----
def _holidays(cfg: dict) -> set[date]:
    out = set()
    for h in cfg.get("holidays", []):
        try:
            out.add(date.fromisoformat(h))
        except ValueError:
            continue
    return out


def is_business_day(d: date, hol: set[date]) -> bool:
    return d.weekday() < 5 and d not in hol


def compute_due(publish: date, offset: int, cfg: dict) -> date:
    """발간일 기준 D-offset 마감일. 영업일 기준이면 영업일 수로 세고, 달력일 기준이면 휴일·주말에 걸릴 때 설정 방식으로 조정한다."""
    hol = _holidays(cfg)
    if offset == 0:
        return publish
    if cfg.get("day_basis") == "business":
        d, left = publish, offset
        while left > 0:
            d -= timedelta(days=1)
            if is_business_day(d, hol):
                left -= 1
        return d
    d = publish - timedelta(days=offset)
    rule = cfg.get("holiday_rule", "prev")
    if rule in ("prev", "next"):
        step = -1 if rule == "prev" else 1
        guard = 0
        while not is_business_day(d, hol) and guard < 30:
            d += timedelta(days=step)
            guard += 1
    return d


def ensure_steps(db: Session, issue: JournalIssue) -> list[JournalScheduleStep]:
    cfg = get_settings(db)
    existing = {s.step_key: s for s in db.scalars(select(JournalScheduleStep).where(JournalScheduleStep.issue_id == issue.id)).all()}
    for pos, tpl in enumerate(cfg["schedule_steps"]):
        step = existing.get(tpl["key"])
        if step is None:
            step = JournalScheduleStep(issue_id=issue.id, step_key=tpl["key"], label=tpl["label"], offset_days=tpl["offset_days"],
                                       window_start_days=tpl.get("window_start_days"), position=pos)
            db.add(step)
            existing[tpl["key"]] = step
        else:
            step.label, step.offset_days, step.window_start_days, step.position = tpl["label"], tpl["offset_days"], tpl.get("window_start_days"), pos
    db.flush()
    recompute_due_dates(db, issue, cfg)
    return sorted(existing.values(), key=lambda s: s.position)


def recompute_due_dates(db: Session, issue: JournalIssue, cfg: dict | None = None) -> None:
    """발간일이 입력·변경되면 마감일을 다시 계산한다. 실제 완료일(completed_at)은 건드리지 않는다."""
    cfg = cfg or get_settings(db)
    for step in db.scalars(select(JournalScheduleStep).where(JournalScheduleStep.issue_id == issue.id)).all():
        if issue.publish_date is None:
            step.due_date = step.window_start_date = None
            continue
        step.due_date = compute_due(issue.publish_date, step.offset_days, cfg)
        step.window_start_date = compute_due(issue.publish_date, step.window_start_days, cfg) if step.window_start_days else None
    db.flush()


def step_state(step: JournalScheduleStep, on: date, due_soon_days: int = 3) -> str:
    if step.completed_at is not None:
        return "done"
    if step.due_date is None:
        return "no_date"
    if step.due_date < on:
        return "delayed"
    if (step.due_date - on).days <= due_soon_days:
        return "due_soon"
    return "upcoming"


def step_out(step: JournalScheduleStep, steps: list[JournalScheduleStep], on: date, due_soon_days: int) -> dict:
    state = step_state(step, on, due_soon_days)
    impact = None
    if state == "delayed":
        nxt = next((s for s in steps if s.position > step.position and s.completed_at is None and s.due_date), None)
        late = (on - step.due_date).days
        if nxt:
            slack = (nxt.due_date - on).days
            impact = f"{late}일 지연 — 다음 단계 '{nxt.label}' 마감({nxt.due_date.isoformat()})까지 {slack}일 남음" + (
                " (이미 마감일이 지났습니다)" if slack < 0 else "")
        else:
            impact = f"{late}일 지연"
    return {
        "id": str(step.id), "step_key": step.step_key, "label": step.label, "offset_days": step.offset_days,
        "window_start_days": step.window_start_days, "due_date": step.due_date.isoformat() if step.due_date else None,
        "window_start_date": step.window_start_date.isoformat() if step.window_start_date else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None, "state": state, "impact": impact, "note": step.note,
    }


def issue_label(issue: JournalIssue) -> str:
    return f"{issue.year}년 제{issue.issue_no}호"


def issue_out(db: Session, issue: JournalIssue, on: date | None = None) -> dict:
    on = on or today()
    cfg = get_settings(db)
    steps = list(db.scalars(select(JournalScheduleStep).where(JournalScheduleStep.issue_id == issue.id).order_by(JournalScheduleStep.position)).all())
    editor = db.get(User, issue.editor_user_id) if issue.editor_user_id else None
    return {
        "id": str(issue.id), "year": issue.year, "issue_no": issue.issue_no, "label": issue_label(issue),
        "publish_date": issue.publish_date.isoformat() if issue.publish_date else None, "status": issue.status,
        "status_label": ISSUE_STATUS_LABELS.get(issue.status, issue.status), "tech_field": issue.tech_field, "topic": issue.topic,
        "editor_user_id": str(issue.editor_user_id) if issue.editor_user_id else None, "editor_name": editor.display_name if editor else None,
        "iitp_confirmed": issue.iitp_confirmed, "iitp_note": issue.iitp_note,
        "published_at": issue.published_at.isoformat() if issue.published_at else None, "is_synthetic": issue.is_synthetic, "note": issue.note,
        "steps": [step_out(s, steps, on, cfg["due_soon_days"]) for s in steps],
    }


# ---------------------------------------------------------------- 전문가 ----
def next_expert_code(db: Session) -> str:
    n = db.scalar(select(func.count()).select_from(JournalExpert)) or 0
    while True:
        n += 1
        code = f"E-{n:04d}"
        if db.scalar(select(JournalExpert.id).where(JournalExpert.expert_code == code)) is None:
            return code


def _key(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def find_duplicate_expert(db: Session, name: str, affiliation: str, email: str | None, exclude: uuid.UUID | None = None) -> JournalExpert | None:
    for e in db.scalars(select(JournalExpert).where(JournalExpert.anonymized.is_(False))).all():
        if exclude and e.id == exclude:
            continue
        if email and e.email and _key(e.email) == _key(email):
            return e
        if _key(e.name) == _key(name) and _key(e.affiliation) == _key(affiliation):
            return e
    return None


def expert_out(db: Session, e: JournalExpert, detail: bool = True) -> dict:
    history = []
    if detail:
        for m in db.scalars(select(JournalManuscript).where(JournalManuscript.expert_id == e.id).order_by(JournalManuscript.created_at)).all():
            issue = db.get(JournalIssue, m.issue_id)
            history.append({"manuscript_id": str(m.id), "title": m.title, "issue": issue_label(issue) if issue else None,
                            "status": m.status, "status_label": STATUS_LABELS.get(m.status, m.status)})
    commissions = db.scalars(select(JournalCommission).where(JournalCommission.expert_id == e.id)).all()
    counts = {k: sum(1 for c in commissions if c.status == k) for k in COMMISSION_STATUS_LABELS}
    return {
        "id": str(e.id), "expert_code": e.expert_code, "name": e.name, "affiliation": e.affiliation, "department": e.department,
        "position_title": e.position_title, "fields": json.loads(e.fields_json or "[]"), "research_summary": e.research_summary,
        "email": e.email, "phone": e.phone, "consent_status": e.consent_status,
        "consent_at": e.consent_at.isoformat() if e.consent_at else None, "consent_note": e.consent_note,
        "retention_until": e.retention_until.isoformat() if e.retention_until else None, "anonymized": e.anonymized,
        "user_id": str(e.user_id) if e.user_id else None, "is_synthetic": e.is_synthetic, "notes": e.notes,
        "commission_counts": counts, "history": history,
    }


def search_experts(db: Session, q: str | None, field: str | None, only_available: bool = False) -> list[dict]:
    """등록된 전문분야·집필 이력 기준 후보 검색. 실제 집필 가능 여부는 판단하지 않는다(의뢰 응답 이력만 보여준다)."""
    rows = db.scalars(select(JournalExpert).where(JournalExpert.anonymized.is_(False)).order_by(JournalExpert.name)).all()
    out = []
    for e in rows:
        fields = json.loads(e.fields_json or "[]")
        blob = " ".join([e.name, e.affiliation, e.department or "", e.research_summary or "", " ".join(fields)]).lower()
        if q and q.lower() not in blob:
            continue
        if field and field not in fields:
            continue
        o = expert_out(db, e, detail=False)
        o["accepted_before"] = db.scalar(select(func.count()).select_from(JournalManuscript).where(JournalManuscript.expert_id == e.id)) or 0
        o["note"] = "집필 가능 여부는 의뢰 후 응답으로만 확인합니다"
        out.append(o)
    out.sort(key=lambda x: (-x["accepted_before"], x["name"]))
    return out


# ---------------------------------------------------------------- 의뢰 ----
def log_commission(db: Session, c: JournalCommission, event: str, user_id: uuid.UUID | None, frm: str | None = None, to: str | None = None,
                   note: str | None = None) -> None:
    db.add(JournalCommissionEvent(commission_id=c.id, event=event, from_status=frm, to_status=to, note=note, user_id=user_id))


def change_commission_status(db: Session, c: JournalCommission, to: str, user_id: uuid.UUID, note: str | None = None) -> None:
    if to == c.status:
        return
    if to not in COMMISSION_TRANSITIONS.get(c.status, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{COMMISSION_STATUS_LABELS[c.status]}' 상태에서 '{COMMISSION_STATUS_LABELS.get(to, to)}'(으)로 바꿀 수 없습니다")
    frm = c.status
    c.status = to
    if to == "requested":
        c.requested_at = now()
    if to in ("accepted", "declined", "no_response"):
        c.responded_at = now() if to != "no_response" else c.responded_at
        if note:
            c.response_note = note
    log_commission(db, c, "status_change", user_id, frm, to, note)
    if to == "accepted":
        ensure_manuscript_for_commission(db, c, user_id)
    db.flush()


def ensure_manuscript_for_commission(db: Session, c: JournalCommission, user_id: uuid.UUID) -> JournalManuscript:
    ms = db.scalar(select(JournalManuscript).where(JournalManuscript.commission_id == c.id))
    if ms is None:
        expert = db.get(JournalExpert, c.expert_id)
        ms = JournalManuscript(
            commission_id=c.id, issue_id=c.issue_id, expert_id=c.expert_id, title=c.topic, status="received",
            authors_json=json.dumps([{"name": expert.name, "affiliation": expert.affiliation, "corresponding": True}], ensure_ascii=False),
            is_synthetic=bool(expert.is_synthetic), version_count=0,
        )
        db.add(ms)
        db.flush()
    return ms


def mail_draft(db: Session, c: JournalCommission) -> dict:
    """집필 의뢰 안내 메일 초안(미리보기·임시저장 전용 — 발송하지 않는다)."""
    expert = db.get(JournalExpert, c.expert_id)
    issue = db.get(JournalIssue, c.issue_id)
    lines = [f"{expert.name} {expert.position_title or '선생님'}께,", "",
             f"주간기술동향지 {issue_label(issue)} 원고 집필을 아래와 같이 의뢰드립니다.", "",
             f"- 집필 요청 주제: {c.topic}"]
    for label, val in (("작성 취지", c.purpose), ("권장 목차·주요 내용", c.outline), ("원고 분량", c.length_spec), ("양식", c.format_spec),
                       ("제출 방법", c.delivery_method), ("담당자 연락처", c.contact_info)):
        if val:
            lines.append(f"- {label}: {val}")
    lines.append(f"- 제출 기한: {c.due_date.isoformat() if c.due_date else '(미정 — 확정 후 안내)'}")
    lines += ["", "※ 이 안내문은 작성·미리보기용 임시 초안이며 아직 발송되지 않았습니다. 발간 일정은 확정 전일 수 있습니다."]
    return {"subject": f"[주간기술동향지] {issue_label(issue)} 원고 집필 의뢰 — {c.topic[:40]}", "body": "\n".join(lines)}


def commission_out(db: Session, c: JournalCommission, include_events: bool = False) -> dict:
    expert = db.get(JournalExpert, c.expert_id)
    issue = db.get(JournalIssue, c.issue_id)
    ms = db.scalar(select(JournalManuscript).where(JournalManuscript.commission_id == c.id))
    out = {
        "id": str(c.id), "issue_id": str(c.issue_id), "issue_label": issue_label(issue), "expert_id": str(c.expert_id),
        "expert_name": expert.name if expert else None, "expert_code": expert.expert_code if expert else None, "topic": c.topic,
        "purpose": c.purpose, "outline": c.outline, "length_spec": c.length_spec, "format_spec": c.format_spec,
        "due_date": c.due_date.isoformat() if c.due_date else None, "delivery_method": c.delivery_method, "contact_info": c.contact_info,
        "candidate_id": str(c.candidate_id) if c.candidate_id else None, "status": c.status, "status_label": COMMISSION_STATUS_LABELS[c.status],
        "mail_subject": c.mail_subject, "mail_body": c.mail_body, "mail_status": c.mail_status,
        "mail_notice": "실제 이메일은 발송되지 않습니다(작성·임시저장·발송 대기 기록만 관리)",
        "requested_at": c.requested_at.isoformat() if c.requested_at else None,
        "responded_at": c.responded_at.isoformat() if c.responded_at else None, "response_note": c.response_note,
        "manuscript_id": str(ms.id) if ms else None, "delay": commission_delay(c, today()),
    }
    if include_events:
        out["events"] = [{"event": e.event, "from": e.from_status, "to": e.to_status, "note": e.note, "at": e.created_at.isoformat()}
                         for e in db.scalars(select(JournalCommissionEvent).where(JournalCommissionEvent.commission_id == c.id)
                                             .order_by(JournalCommissionEvent.created_at)).all()]
    return out


def commission_delay(c: JournalCommission, on: date) -> str | None:
    if not c.due_date:
        return None
    if c.status == "accepted":
        return None  # 제출 여부는 원고 접수 상태로 판단(아래 manuscript_overdue)
    return None


# ---------------------------------------------------------------- 원고 ----
def check_transition(ms: JournalManuscript, to: str) -> None:
    if to not in TRANSITIONS.get(ms.status, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{STATUS_LABELS[ms.status]}' 상태에서 '{STATUS_LABELS.get(to, to)}'(으)로 바꿀 수 없습니다")


def set_status(ms: JournalManuscript, to: str) -> None:
    check_transition(ms, to)
    ms.status = to
    ms.lock_version += 1


def attachment_keys(db: Session, ms: JournalManuscript) -> list[str]:
    return sorted({a.doc_type for a in db.scalars(select(JournalAttachment).where(JournalAttachment.manuscript_id == ms.id)).all()})


def _meta(ms: JournalManuscript) -> dict:
    return {"title": ms.title, "title_en": ms.title_en, "summary": ms.summary, "authors": json.loads(ms.authors_json or "[]"),
            "references_text": ms.references_text}


def submit_version(db: Session, ms: JournalManuscript, user: User, file_name: str, data: bytes, kind: str, note: str | None) -> JournalVersion:
    """원고 파일을 새 버전으로 접수한다(기존 파일 덮어쓰기 없음). 보안 검사에서 거부되면 UploadRejected."""
    cfg = get_settings(db)
    scan = journal_files.scan_upload(file_name, data, cfg["manuscript_ext"], int(cfg["max_upload_mb"]) * 1024 * 1024)
    ext = scan["ext"]
    path, digest = journal_files.store("manuscripts", ms.id, file_name, data)
    ex = journal_docx.extract(data, ext)
    version_no = (db.scalar(select(func.max(JournalVersion.version_no)).where(JournalVersion.manuscript_id == ms.id)) or 0) + 1
    fc = journal_docx.format_check(ex, _meta(ms), cfg, attachment_keys(db, ms))
    prev = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
    extract_store = {k: v for k, v in ex.items() if k not in ("paragraphs", "para_meta")}
    extract_store["paragraph_count"] = len(ex.get("paragraphs", []))
    if prev is not None and kind == "revision":
        prev_ex = journal_docx.extract(journal_files.read(prev.file_path), journal_files.ext_of(prev.file_name))
        cmp = journal_docx.compare_versions(prev_ex, ex)
        total = max(len(prev_ex.get("paragraphs", [])), len(ex.get("paragraphs", [])), 1)
        changed = sum(cmp["counts"].values())
        extract_store["change_vs_prev"] = {"counts": cmp["counts"], "ratio": round(changed / total, 2), "prev_version_no": prev.version_no,
                                           "needs_original_compare": cmp["needs_original_compare"]}
    ver = JournalVersion(
        manuscript_id=ms.id, version_no=version_no, kind=kind, file_name=journal_files.safe_name(file_name), file_path=path, file_size=len(data),
        sha256=digest, mime=journal_files.MIME_BY_EXT.get(ext), uploaded_by_user_id=user.id, note=note, scan_json=json.dumps(scan, ensure_ascii=False),
        extract_json=json.dumps(extract_store, ensure_ascii=False), format_check_json=json.dumps(fc, ensure_ascii=False),
        snapshot_title=ms.title, snapshot_authors_json=ms.authors_json,
    )
    db.add(ver)
    ms.version_count = version_no
    ms.lock_version += 1
    if kind == "submission":
        ms.submitted_at = ms.submitted_at or now()
    db.flush()
    return ver


def apply_submission_status(ms: JournalManuscript, ver: JournalVersion) -> None:
    """제출 직후 상태: 최초·재제출은 형식 점검 결과에 따라 '접수 완료/형식 보완 필요', 수정본은 '수정본 접수'."""
    fc = json.loads(ver.format_check_json or "{}")
    if ver.kind == "revision":
        ms.status = "revision_received"
        ms.content_status = "pending"
        return
    ms.format_status = fc.get("result", "needs_fix")
    ms.status = "format_fix_needed" if fc.get("needs_fix") else "received"


def version_out(db: Session, v: JournalVersion) -> dict:
    uploader = db.get(User, v.uploaded_by_user_id)
    return {
        "id": str(v.id), "version_no": v.version_no, "kind": v.kind,
        "kind_label": {"submission": "최초 제출", "revision": "수정본", "proofread": "교정본"}.get(v.kind, v.kind),
        "file_name": v.file_name, "file_size": v.file_size, "sha256": v.sha256, "uploaded_at": v.created_at.isoformat(),
        "uploaded_by": uploader.display_name if uploader else None, "note": v.note, "scan": json.loads(v.scan_json or "{}"),
        "extract": json.loads(v.extract_json or "{}"), "format_check": json.loads(v.format_check_json or "{}"),
        "proof_checklist": json.loads(v.proof_checklist_json) if v.proof_checklist_json else None,
        "snapshot_title": v.snapshot_title,
    }


def comment_out(db: Session, c: JournalComment, *, anonymize: bool) -> dict:
    author = db.get(User, c.author_user_id)
    ver = db.get(JournalVersion, c.version_id) if c.version_id else None
    return {
        "id": str(c.id), "kind": c.kind, "scope": c.scope, "anchor_text": c.anchor_text, "anchor_index": c.anchor_index, "text": c.text,
        "requires_revision": c.requires_revision, "status": c.status, "author_reply": c.author_reply,
        "replied_at": c.replied_at.isoformat() if c.replied_at else None,
        "author_name": ("검토자" if anonymize else (author.display_name if author else None)), "created_at": c.created_at.isoformat(),
        "version_no": ver.version_no if ver else None, "assignment_id": str(c.assignment_id) if c.assignment_id else None,
        "reply_version_id": str(c.reply_version_id) if c.reply_version_id else None,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
    }


def assignment_out(db: Session, a: JournalAssignment) -> dict:
    reviewer = db.get(User, a.reviewer_user_id)
    return {
        "id": str(a.id), "manuscript_id": str(a.manuscript_id), "reviewer_user_id": str(a.reviewer_user_id),
        "reviewer_name": reviewer.display_name if reviewer else None, "round": a.round, "role_kind": a.role_kind,
        "due_date": a.due_date.isoformat() if a.due_date else None, "status": a.status, "conflict_declared": a.conflict_declared,
        "conflict_checked": a.conflict_checked, "conflict_note": a.conflict_note, "recommendation": a.recommendation,
        "summary_opinion": a.summary_opinion, "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "overdue": bool(a.due_date and a.status != "completed" and a.due_date < today()),
    }


def manuscript_out(db: Session, ms: JournalManuscript, *, for_author: bool = False) -> dict:
    expert = db.get(JournalExpert, ms.expert_id)
    issue = db.get(JournalIssue, ms.issue_id)
    versions = list(db.scalars(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no)).all())
    comments = list(db.scalars(select(JournalComment).where(JournalComment.manuscript_id == ms.id).order_by(JournalComment.created_at)).all())
    cfg = get_settings(db)
    out = {
        "id": str(ms.id), "issue_id": str(ms.issue_id), "issue_label": issue_label(issue), "commission_id": str(ms.commission_id),
        "expert_id": str(ms.expert_id), "expert_name": expert.name if expert else None, "title": ms.title, "title_en": ms.title_en,
        "summary": ms.summary, "authors": json.loads(ms.authors_json or "[]"), "references_text": ms.references_text, "status": ms.status,
        "status_label": STATUS_LABELS.get(ms.status, ms.status), "format_status": ms.format_status, "content_status": ms.content_status,
        "copyright_confirmed": ms.copyright_confirmed, "third_party_note": ms.third_party_note, "lock_version": ms.lock_version,
        "version_count": ms.version_count, "is_synthetic": ms.is_synthetic, "submitted_at": ms.submitted_at.isoformat() if ms.submitted_at else None,
        "versions": [version_out(db, v) for v in versions], "comments": [comment_out(db, c, anonymize=for_author) for c in comments],
        "attachments": [{"id": str(a.id), "doc_type": a.doc_type, "file_name": a.file_name, "file_size": a.file_size, "sha256": a.sha256,
                         "uploaded_at": a.created_at.isoformat(), "scan": json.loads(a.scan_json or "{}")}
                        for a in db.scalars(select(JournalAttachment).where(JournalAttachment.manuscript_id == ms.id)).all()],
        "required_docs": cfg["required_docs"], "proof_confirmed": ms.proof_confirmed_at is not None,
        "outcomes": cfg["decision_outcomes"],
        "open_comment_count": sum(1 for c in comments if c.status != "resolved" and c.requires_revision),
    }
    last = versions[-1] if versions else None
    if last:
        ch = json.loads(last.extract_json or "{}").get("change_vs_prev")
        if ch:
            out["review_validity"] = {
                "change_ratio": ch["ratio"], "threshold": cfg["major_change_ratio"], "needs_rereview": ch["ratio"] >= cfg["major_change_ratio"],
                "message": ("수정 폭이 커서 이전 검토 결과가 그대로 유효한지 재검토가 필요합니다" if ch["ratio"] >= cfg["major_change_ratio"] else None),
            }
    if not for_author:
        out["assignments"] = [assignment_out(db, a) for a in db.scalars(select(JournalAssignment).where(JournalAssignment.manuscript_id == ms.id)
                                                                           .order_by(JournalAssignment.round, JournalAssignment.created_at)).all()]
        out["decisions"] = [{"id": str(d.id), "round": d.round, "outcome": d.outcome, "note": d.note, "is_final": d.is_final,
                             "exception_reason": d.exception_reason, "unresolved_count": d.unresolved_count,
                             "decided_by": (db.get(User, d.decided_by_user_id).display_name if db.get(User, d.decided_by_user_id) else None),
                             "decided_at": d.created_at.isoformat()} for d in db.scalars(select(JournalDecision).where(JournalDecision.manuscript_id == ms.id)
                                                                                         .order_by(JournalDecision.created_at)).all()]
        out["plagiarism"] = [{"id": str(p.id), "service_name": p.service_name, "file_name": p.file_name, "similarity_pct": p.similarity_pct,
                              "status": p.status, "note": p.note, "uploaded_at": p.created_at.isoformat(),
                              "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None}
                             for p in db.scalars(select(JournalPlagiarism).where(JournalPlagiarism.manuscript_id == ms.id)).all()]
        out["plagiarism_notice"] = "외부 표절검사 서비스와 연동되어 있지 않습니다 — 결과 파일을 올리고 담당자가 확인한 기록만 관리합니다"
    return out


# ---------------------------------------------------------------- 대시보드·알림 ----
def dashboard(db: Session, year: int | None, editor_id: uuid.UUID | None = None, on: date | None = None) -> dict:
    on = on or today()
    cfg = get_settings(db)
    stmt = select(JournalIssue)
    if year:
        stmt = stmt.where(JournalIssue.year == year)
    issues = list(db.scalars(stmt.order_by(JournalIssue.year, JournalIssue.issue_no)).all())
    ids = [i.id for i in issues]
    manuscripts = list(db.scalars(select(JournalManuscript).where(JournalManuscript.issue_id.in_(ids))).all()) if ids else []
    commissions = list(db.scalars(select(JournalCommission).where(JournalCommission.issue_id.in_(ids))).all()) if ids else []
    steps = list(db.scalars(select(JournalScheduleStep).where(JournalScheduleStep.issue_id.in_(ids))).all()) if ids else []
    assignments = list(db.scalars(select(JournalAssignment).where(JournalAssignment.manuscript_id.in_([m.id for m in manuscripts]))).all()) if manuscripts else []
    by_issue = {i.id: i for i in issues}
    steps_by_issue: dict[uuid.UUID, list[JournalScheduleStep]] = {}
    for s in steps:
        steps_by_issue.setdefault(s.issue_id, []).append(s)

    delayed, upcoming = [], []
    for s in steps:
        state = step_state(s, on, cfg["due_soon_days"])
        issue = by_issue[s.issue_id]
        if state in ("delayed", "due_soon"):
            row = {"kind": "step", "issue_id": str(issue.id), "issue_label": issue_label(issue), "label": s.label,
                   "due_date": s.due_date.isoformat(), "state": state, "days": (s.due_date - on).days}
            (delayed if state == "delayed" else upcoming).append(row)
    for c in commissions:
        if c.due_date and c.status in ("accepted",):
            ms = next((m for m in manuscripts if m.commission_id == c.id), None)
            if ms is not None and ms.version_count == 0:
                issue = by_issue[c.issue_id]
                days = (c.due_date - on).days
                if days < 0:
                    delayed.append({"kind": "manuscript_due", "issue_id": str(issue.id), "issue_label": issue_label(issue),
                                    "label": f"원고 미제출(집필 마감 경과): {c.topic[:40]}", "due_date": c.due_date.isoformat(), "state": "delayed", "days": days})
                elif days <= cfg["due_soon_days"]:
                    upcoming.append({"kind": "manuscript_due", "issue_id": str(issue.id), "issue_label": issue_label(issue),
                                     "label": f"집필 마감 임박: {c.topic[:40]}", "due_date": c.due_date.isoformat(), "state": "due_soon", "days": days})
    for a in assignments:
        if a.due_date and a.status != "completed":
            ms = next((m for m in manuscripts if m.id == a.manuscript_id), None)
            issue = by_issue[ms.issue_id] if ms else None
            if issue is None:
                continue
            days = (a.due_date - on).days
            if days < 0 or days <= cfg["due_soon_days"]:
                row = {"kind": "review_due", "issue_id": str(issue.id), "issue_label": issue_label(issue), "label": f"검토 기한: {ms.title[:40]}",
                       "due_date": a.due_date.isoformat(), "state": "delayed" if days < 0 else "due_soon", "days": days}
                (delayed if days < 0 else upcoming).append(row)

    unresolved = {}
    for c in db.scalars(select(JournalComment).where(JournalComment.manuscript_id.in_([m.id for m in manuscripts]), JournalComment.status != "resolved",
                                                     JournalComment.requires_revision.is_(True))).all() if manuscripts else []:
        unresolved[c.manuscript_id] = unresolved.get(c.manuscript_id, 0) + 1

    def count(items, key):
        out: dict[str, int] = {}
        for x in items:
            out[getattr(x, key)] = out.get(getattr(x, key), 0) + 1
        return out

    rows = []
    for i in issues:
        ms_i = [m for m in manuscripts if m.issue_id == i.id]
        if editor_id and i.editor_user_id != editor_id:
            continue
        rows.append({
            "id": str(i.id), "label": issue_label(i), "publish_date": i.publish_date.isoformat() if i.publish_date else None,
            "status": i.status, "status_label": ISSUE_STATUS_LABELS.get(i.status, i.status), "topic": i.topic, "tech_field": i.tech_field,
            "editor_user_id": str(i.editor_user_id) if i.editor_user_id else None, "iitp_confirmed": i.iitp_confirmed,
            "commissions": sum(1 for c in commissions if c.issue_id == i.id), "accepted": sum(1 for c in commissions if c.issue_id == i.id and c.status == "accepted"),
            "manuscripts": len(ms_i), "accepted_manuscripts": sum(1 for m in ms_i if m.status == "accepted"),
            "delayed_steps": sum(1 for s in steps_by_issue.get(i.id, []) if step_state(s, on, cfg["due_soon_days"]) == "delayed"),
            "unresolved_comments": sum(unresolved.get(m.id, 0) for m in ms_i),
            "exception_decisions": sum(1 for d in db.scalars(select(JournalDecision).where(JournalDecision.manuscript_id.in_([m.id for m in ms_i]),
                                                                                         JournalDecision.exception_reason.is_not(None))).all()) if ms_i else 0,
        })
    return {
        "year": year, "today": on.isoformat(),
        "plan": {"planned_issues": len(issues), "with_publish_date": sum(1 for i in issues if i.publish_date),
                 "published_records": sum(1 for i in issues if i.status == "published"),
                 "iitp_confirmed": sum(1 for i in issues if i.iitp_confirmed),
                 "note": "계획 건수와 실제 발간 기록 건수는 데이터베이스 기준으로 따로 계산합니다"},
        "commission_status": count(commissions, "status"), "manuscript_status": count(manuscripts, "status"),
        "review": {"assigned": sum(1 for a in assignments if a.status != "completed"), "completed": sum(1 for a in assignments if a.status == "completed")},
        "unresolved_comments": [{"manuscript_id": str(mid), "title": next((m.title for m in manuscripts if m.id == mid), ""), "count": n}
                                for mid, n in unresolved.items()],
        "delayed": sorted(delayed, key=lambda r: r["days"]), "upcoming": sorted(upcoming, key=lambda r: r["days"]), "issues": rows,
    }


# ---------------------------------------------------------------- 발간본 ----
TEMPLATE_VERSION_KEY = "export_template"
JOURNAL_TEMPLATE_BASE = {"name": "주간기술동향지 임시 템플릿", "is_provisional": True}


def export_preflight(db: Session, issue: JournalIssue, items: list[JournalIssueItem]) -> list[dict]:
    out: list[dict] = []

    def add(level, code, msg, ms_id=None):
        out.append({"level": level, "code": code, "message": msg, "manuscript_id": str(ms_id) if ms_id else None})

    if not items:
        add("error", "no_items", "회차에 배치된 게재 원고가 없습니다")
    for it in items:
        ms = db.get(JournalManuscript, it.manuscript_id)
        ver = db.get(JournalVersion, it.version_id)
        if ms.status != "accepted":
            add("error", "not_accepted", f"'{ms.title[:30]}'은(는) 게재 확정되지 않았습니다({STATUS_LABELS[ms.status]})", ms.id)
        if ms.proof_confirmed_at is None:
            add("error", "proof_not_confirmed", f"'{ms.title[:30]}'의 최종 교정 확인이 되지 않았습니다", ms.id)
        if not ms.copyright_confirmed:
            add("warn", "copyright_unconfirmed", f"'{ms.title[:30]}'의 저작권·이용 동의 확인 기록이 없습니다", ms.id)
        if journal_files.ext_of(ver.file_name) != "docx":
            add("error", "not_docx", f"'{ms.title[:30]}'은(는) DOCX가 아니라 본문을 자동 변환할 수 없습니다 — DOCX 교정본이 필요합니다", ms.id)
        ex = json.loads(ver.extract_json or "{}")
        if ex.get("unsupported"):
            add("warn", "unsupported_elements", f"'{ms.title[:30]}': " + ", ".join(ex["unsupported"]) + " — 발간본에 자동 반영되지 않으므로 원본 파일과 대조하세요", ms.id)
        plag = db.scalars(select(JournalPlagiarism).where(JournalPlagiarism.manuscript_id == ms.id)).all()
        if not any(p.status == "confirmed" for p in plag):
            add("warn", "plagiarism_unconfirmed", f"'{ms.title[:30]}'의 표절검사 결과 확인 기록이 없습니다(외부 서비스 미연동)", ms.id)
    if not issue.iitp_confirmed:
        add("info", "iitp_unconfirmed", "IITP 공식 확인 전입니다 — 내부 확정과 별개이며 발간본에 'IITP 확인 전'으로 표시됩니다")
    return out


def export_blocking(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i["level"] == "error"]


def _template(db: Session) -> dict:
    row = db.scalar(select(JournalSetting).where(JournalSetting.key == TEMPLATE_VERSION_KEY))
    data = json.loads(row.value_json) if row else {}
    return {"name": JOURNAL_TEMPLATE_BASE["name"], "version": data.get("version", 1), "is_provisional": True,
            "config": {"header_text": "주간기술동향지", **data.get("config", {})}}


def build_snapshot(db: Session, issue: JournalIssue, items: list[JournalIssueItem], final: bool) -> dict:
    parts = []
    skipped_all: list[str] = []
    for idx, it in enumerate(items):
        ms = db.get(JournalManuscript, it.manuscript_id)
        ver = db.get(JournalVersion, it.version_id)
        authors = json.loads(ver.snapshot_authors_json or ms.authors_json or "[]")
        byline = ", ".join(f"{a['name']}({a['affiliation']})" for a in authors if a.get("name"))
        try:
            body, skipped = journal_docx.to_editor_json(journal_files.read(ver.file_path)) if journal_files.ext_of(ver.file_name) == "docx" else (
                {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "(PDF 원고는 본문을 자동 변환할 수 없습니다 — 원본 파일을 확인하세요)"}]}]}, [])
        except Exception as exc:
            body, skipped = ({"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"(본문 변환 실패: {type(exc).__name__})"}]}]}, [])
        if skipped:
            skipped_all.append(f"{ms.title[:20]}: " + ", ".join(skipped))
        parts.append({
            "key": f"article_{idx + 1}", "heading": f"{idx + 1}. {ver.snapshot_title or ms.title}", "required": True, "summary_items": [],
            "manuscripts": [{"id": str(ms.id), "title": ms.title, "title_en": ms.title_en, "hide_title": True, "body_json": body, "footnotes": {},
                             "byline": byline, "summary": ms.summary, "version_no": ver.version_no, "status_note": None}],
        })
    tpl = _template(db)
    return {
        "report": {
            "id": str(issue.id), "type": "journal", "kind_label": "주간기술동향지", "title": f"주간기술동향지 {issue_label(issue)}", "title_en": None,
            "edition_label": issue_label(issue), "publish_date": issue.publish_date.isoformat() if issue.publish_date else None,
            "iitp_confirmed": issue.iitp_confirmed, "is_pilot": bool(issue.is_synthetic), "status": "final" if final else "draft",
            "layout": "standard", "exception": False, "followups_open": [],
        },
        "template": {"id": "journal-template", "name": tpl["name"], "version": tpl["version"], "is_provisional": True, "config": tpl["config"]},
        "parts": parts, "skipped": skipped_all,
    }


class ExportInProgressError(Exception):
    pass


def generate_export(db: Session, issue: JournalIssue, *, file_format: str, user_id: uuid.UUID, final: bool = False) -> JournalExport:
    if file_format not in ("docx", "pdf"):
        raise ValueError("지원하지 않는 형식입니다")
    recent = now() - timedelta(minutes=5)
    for r in db.scalars(select(JournalExport).where(JournalExport.issue_id == issue.id, JournalExport.file_format == file_format,
                                                     JournalExport.status == "running")).all():
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        if created > recent:
            raise ExportInProgressError("같은 회차의 같은 형식 출력이 이미 진행 중입니다")
        r.status, r.error_message = "failed", "시간 초과로 중단된 이전 요청"
    items = list(db.scalars(select(JournalIssueItem).where(JournalIssueItem.issue_id == issue.id).order_by(JournalIssueItem.position)).all())
    issues = export_preflight(db, issue, items)
    snapshot = build_snapshot(db, issue, items, final)  # 이 시점에 원고 버전·파일을 고정한다
    pinned = [{"manuscript_id": str(i.manuscript_id), "version_id": str(i.version_id),
               "sha256": db.get(JournalVersion, i.version_id).sha256, "version_no": db.get(JournalVersion, i.version_id).version_no}
              for i in items]
    export = JournalExport(issue_id=issue.id, file_format=file_format, status="running", template_version=snapshot["template"]["version"],
                           items_json=json.dumps(pinned, ensure_ascii=False), is_final=final, issue_state=issue.status, created_by_user_id=user_id)
    db.add(export)
    db.commit()
    try:
        built = report_docx.build_docx(snapshot)
        docx_bytes, pdf_bytes, analysis, toc_verified = built.docx_bytes, None, None, None
        if report_pdf.find_soffice() is not None:
            pdf_bytes = report_pdf.convert_docx_to_pdf(built.docx_bytes)
            analysis = report_pdf.analyze_pdf(pdf_bytes, built.headings, built.part_headings)
            toc_verified = False
            for _ in range(3):
                pages = analysis["heading_page_list"]
                built = report_docx.build_docx(snapshot, pages)
                docx_bytes = built.docx_bytes
                pdf_bytes = report_pdf.convert_docx_to_pdf(docx_bytes)
                analysis = report_pdf.analyze_pdf(pdf_bytes, built.headings, built.part_headings)
                if analysis["heading_page_list"] == pages:
                    toc_verified = True
                    break
        elif file_format == "pdf":
            raise report_pdf.PdfUnavailableError("이 서버에는 LibreOffice가 없어 PDF를 생성할 수 없습니다")
        else:
            issues.append({"level": "info", "code": "not_rendered", "message": "LibreOffice가 없어 렌더링으로 페이지 수·목차 번호를 확인하지 못했습니다", "manuscript_id": None})
        payload, ext = (pdf_bytes, "pdf") if file_format == "pdf" else (docx_bytes, "docx")
        for s in snapshot["skipped"]:
            issues.append({"level": "warn", "code": "unconverted_elements", "message": f"자동 변환되지 않은 요소: {s}", "manuscript_id": None})
        if analysis is not None:
            export.page_count = analysis["page_count"]
        folder = journal_files.journal_root() / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = now().strftime("%Y%m%d-%H%M%S")
        file_name = f"기술동향지_{issue.year}_{issue.issue_no}호_{stamp}{'_확정' if final else '_초안'}.{ext}"
        path = folder / f"{export.id}.{ext}"
        path.write_bytes(payload)
        export.file_name, export.file_path = file_name, str(path)
        export.file_sha256, export.file_size = hashlib.sha256(payload).hexdigest(), len(payload)
        export.validation_json = json.dumps({
            "issues": issues, "part_pages": analysis["part_pages"] if analysis else None, "rendered": analysis is not None, "toc_verified": toc_verified,
        }, ensure_ascii=False)
        export.status, export.finished_at = "success", now()
        db.commit()
    except Exception as exc:
        db.rollback()
        export = db.get(JournalExport, export.id)
        export.status, export.error_message, export.finished_at = "failed", f"{type(exc).__name__}: {exc}"[:1000], now()
        db.commit()
    db.refresh(export)
    return export


def export_out(e: JournalExport) -> dict:
    return {
        "id": str(e.id), "issue_id": str(e.issue_id), "file_format": e.file_format, "status": e.status, "error_message": e.error_message,
        "template_version": e.template_version, "file_name": e.file_name, "file_sha256": e.file_sha256, "file_size": e.file_size,
        "page_count": e.page_count, "is_final": e.is_final, "items": json.loads(e.items_json or "[]"),
        "validation": json.loads(e.validation_json or "{}"), "issue_state": e.issue_state, "created_at": e.created_at.isoformat(),
        "finished_at": e.finished_at.isoformat() if e.finished_at else None,
    }
