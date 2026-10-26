"""주간기술동향지 편집 API(편집 담당자·승인권자·관리자용). 외부 저자·검토자는 /journal/portal 만 사용한다."""

import json
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import require_roles
from app.core.security import hash_password
from app.models.candidate import Candidate
from app.models.enums import UserRole
from app.models.journal import (
    JournalAssignment, JournalAttachment, JournalCommission, JournalComment, JournalDecision, JournalExpert, JournalExport, JournalIssue,
    JournalIssueItem, JournalManuscript, JournalPlagiarism, JournalScheduleStep, JournalSetting, JournalVersion,
)
from app.models.user import User
from app.services import journal_docx, journal_files
from app.services import journal_service as svc

router = APIRouter(prefix="/journal", tags=["journal"])
editor = require_roles(*svc.EDITOR_ROLES)
decider = require_roles(*svc.DECIDER_ROLES)
admin_only = require_roles(UserRole.ADMIN)


def _get(db: Session, model, obj_id: uuid.UUID, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label}을(를) 찾을 수 없습니다")
    return obj


def _audit(db: Session, user: User, action: str, entity: str, entity_id: uuid.UUID, **detail) -> None:
    log_action(db, actor_user_id=user.id, action=f"journal.{action}", entity_type=entity, entity_id=entity_id, detail=detail or None)


def _upload(db: Session, data_file: UploadFile, allowed_key: str):
    cfg = svc.get_settings(db)
    limit = int(cfg["max_upload_mb"]) * 1024 * 1024
    data = data_file.file.read(limit + 1)
    return cfg, data, limit


# ---------------------------------------------------------------- 설정 ----
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(editor)):
    return svc.get_settings(db)


class SettingsPatch(BaseModel):
    day_basis: Literal["calendar", "business"] | None = None
    holiday_rule: Literal["none", "prev", "next"] | None = None
    holidays: list[date] | None = None
    max_upload_mb: int | None = Field(default=None, ge=1, le=200)
    word_min: int | None = Field(default=None, ge=0)
    word_max: int | None = Field(default=None, ge=0)
    required_docs: list[dict] | None = None
    decision_outcomes: list[dict] | None = None
    major_change_ratio: float | None = Field(default=None, ge=0, le=1)
    retention_months: int | None = Field(default=None, ge=1)
    due_soon_days: int | None = Field(default=None, ge=0, le=30)
    schedule_steps: list[dict] | None = None
    clear: list[str] = []  # 기준값을 '미설정'으로 되돌릴 키(word_min·word_max·retention_months)


@router.patch("/settings")
def patch_settings(payload: SettingsPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    patch = {k: v for k, v in payload.model_dump(exclude={"clear"}).items() if v is not None}
    if "holidays" in patch:
        patch["holidays"] = [d.isoformat() for d in patch["holidays"]]
    for key in payload.clear:
        patch[key] = None
    if "decision_outcomes" in patch:
        valid = all({"key", "label", "effect"} <= set(o) and o["effect"] in ("accept", "revise", "hold", "reject") for o in patch["decision_outcomes"])
        if not valid or not patch["decision_outcomes"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "심의 결과 구분은 key·label·effect(accept/revise/hold/reject)가 필요합니다")
    if "required_docs" in patch and not all({"key", "label"} <= set(d) for d in patch["required_docs"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "제출서류는 key와 label이 필요합니다")
    cfg = svc.set_settings(db, patch, user.id)
    if {"day_basis", "holiday_rule", "holidays", "schedule_steps"} & set(patch):  # 일정 기준이 바뀌면 모든 회차의 마감일을 다시 계산한다
        for issue in db.scalars(select(JournalIssue)).all():
            svc.ensure_steps(db, issue)
    _audit(db, user, "settings.update", "journal_setting", uuid.uuid4(), keys=sorted(patch))
    db.commit()
    return cfg


class TemplatePatch(BaseModel):
    config: dict


@router.get("/template")
def get_template(db: Session = Depends(get_db), _: User = Depends(editor)):
    t = svc._template(db)
    return {**t, "notice": "공식 주간기술동향지 양식이 저장소에 없어 임시 템플릿입니다 — 공식 양식 확보 후 새 버전으로 교체하세요"}


@router.patch("/template")
def patch_template(payload: TemplatePatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    cur = svc._template(db)
    row = db.scalar(select(JournalSetting).where(JournalSetting.key == svc.TEMPLATE_VERSION_KEY))
    if row is None:
        row = JournalSetting(key=svc.TEMPLATE_VERSION_KEY, value_json="{}")
        db.add(row)
    row.value_json = json.dumps({"version": cur["version"] + 1, "config": {**cur["config"], **payload.config}}, ensure_ascii=False)
    row.updated_by_user_id = user.id
    _audit(db, user, "template.new_version", "journal_setting", row.id or uuid.uuid4(), version=cur["version"] + 1)
    db.commit()
    return svc._template(db)


# ---------------------------------------------------------------- 회차 ----
class PlanYear(BaseModel):
    year: int = Field(ge=2000, le=2100)
    count: int = Field(default=25, ge=1, le=60)
    is_synthetic: bool = False


@router.post("/issues/plan-year", status_code=status.HTTP_201_CREATED)
def plan_year(payload: PlanYear, db: Session = Depends(get_db), user: User = Depends(editor)):
    """연간 회차를 등록한다. 발간일은 자동으로 정하지 않는다(관리자가 실제 발간일을 입력해야 마감일이 계산된다)."""
    created = []
    for no in range(1, payload.count + 1):
        if db.scalar(select(JournalIssue.id).where(JournalIssue.year == payload.year, JournalIssue.issue_no == no)):
            continue
        issue = JournalIssue(year=payload.year, issue_no=no, status="planning", is_synthetic=payload.is_synthetic, created_by_user_id=user.id)
        db.add(issue)
        db.flush()
        svc.ensure_steps(db, issue)
        created.append(issue)
    _audit(db, user, "issues.plan_year", "journal_issue", uuid.uuid4(), year=payload.year, created=len(created))
    db.commit()
    return {"created": len(created), "total": db.scalar(select(func.count()).select_from(JournalIssue).where(JournalIssue.year == payload.year))}


class IssueCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    issue_no: int = Field(ge=1, le=100)
    topic: str | None = None
    tech_field: str | None = None


@router.post("/issues", status_code=status.HTTP_201_CREATED)
def create_issue(payload: IssueCreate, db: Session = Depends(get_db), user: User = Depends(editor)):
    if db.scalar(select(JournalIssue.id).where(JournalIssue.year == payload.year, JournalIssue.issue_no == payload.issue_no)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 회차입니다")
    issue = JournalIssue(year=payload.year, issue_no=payload.issue_no, topic=payload.topic, tech_field=payload.tech_field, created_by_user_id=user.id)
    db.add(issue)
    db.flush()
    svc.ensure_steps(db, issue)
    _audit(db, user, "issue.create", "journal_issue", issue.id)
    db.commit()
    return svc.issue_out(db, issue)


@router.get("/issues")
def list_issues(year: int | None = None, db: Session = Depends(get_db), _: User = Depends(editor)):
    stmt = select(JournalIssue).order_by(JournalIssue.year, JournalIssue.issue_no)
    if year:
        stmt = stmt.where(JournalIssue.year == year)
    out = []
    for i in db.scalars(stmt).all():
        o = svc.issue_out(db, i)
        o.pop("steps")
        out.append(o)
    return out


@router.get("/issues/{issue_id}")
def get_issue(issue_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(editor)):
    issue = _get(db, JournalIssue, issue_id, "회차")
    out = svc.issue_out(db, issue)
    out["commissions"] = [svc.commission_out(db, c) for c in db.scalars(select(JournalCommission).where(JournalCommission.issue_id == issue.id)
                                                                         .order_by(JournalCommission.created_at)).all()]
    mss = db.scalars(select(JournalManuscript).where(JournalManuscript.issue_id == issue.id).order_by(JournalManuscript.created_at)).all()
    out["manuscripts"] = [{"id": str(m.id), "title": m.title, "expert_name": (db.get(JournalExpert, m.expert_id).name), "status": m.status,
                           "status_label": svc.STATUS_LABELS[m.status], "version_count": m.version_count, "format_status": m.format_status,
                           "proof_confirmed": m.proof_confirmed_at is not None} for m in mss]
    items = db.scalars(select(JournalIssueItem).where(JournalIssueItem.issue_id == issue.id).order_by(JournalIssueItem.position)).all()
    out["items"] = [{"manuscript_id": str(it.manuscript_id), "version_id": str(it.version_id), "position": it.position,
                     "title": db.get(JournalManuscript, it.manuscript_id).title, "version_no": db.get(JournalVersion, it.version_id).version_no}
                    for it in items]
    out["export_preflight"] = svc.export_preflight(db, issue, list(items))
    out["exports"] = [svc.export_out(e) for e in db.scalars(select(JournalExport).where(JournalExport.issue_id == issue.id)
                                                            .order_by(JournalExport.created_at.desc())).all()]
    return out


class IssuePatch(BaseModel):
    topic: str | None = None
    tech_field: str | None = None
    editor_user_id: uuid.UUID | None = None
    status: Literal["planning", "recruiting", "receiving", "reviewing", "editing", "iitp_check"] | None = None
    note: str | None = None
    publish_date: date | None = None


@router.patch("/issues/{issue_id}")
def patch_issue(issue_id: uuid.UUID, payload: IssuePatch, db: Session = Depends(get_db), user: User = Depends(editor)):
    issue = _get(db, JournalIssue, issue_id, "회차")
    data = payload.model_dump(exclude_unset=True)
    if "publish_date" in data and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "발간일은 관리자만 입력·변경할 수 있습니다")
    if issue.status == "published" and "status" in data:
        raise HTTPException(status.HTTP_409_CONFLICT, "발간 기록된 회차의 상태는 바꿀 수 없습니다")
    for key in ("topic", "tech_field", "note", "status"):
        if key in data:
            setattr(issue, key, data[key])
    if "editor_user_id" in data:
        if data["editor_user_id"] and db.get(User, data["editor_user_id"]) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "담당자를 찾을 수 없습니다")
        issue.editor_user_id = data["editor_user_id"]
    if "publish_date" in data:
        issue.publish_date = data["publish_date"]
        svc.ensure_steps(db, issue)
    _audit(db, user, "issue.update", "journal_issue", issue.id, fields=sorted(data))
    db.commit()
    return svc.issue_out(db, issue)


class StepComplete(BaseModel):
    note: str | None = None


@router.post("/issues/{issue_id}/steps/{step_id}/complete")
def complete_step(issue_id: uuid.UUID, step_id: uuid.UUID, payload: StepComplete, db: Session = Depends(get_db), user: User = Depends(editor)):
    issue = _get(db, JournalIssue, issue_id, "회차")
    step = _get(db, JournalScheduleStep, step_id, "일정 단계")
    if step.issue_id != issue.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정 단계를 찾을 수 없습니다")
    step.completed_at, step.completed_by_user_id, step.note = svc.now(), user.id, payload.note
    _audit(db, user, "step.complete", "journal_issue", issue.id, step=step.step_key)
    db.commit()
    return svc.issue_out(db, issue)


@router.post("/issues/{issue_id}/steps/{step_id}/reopen")
def reopen_step(issue_id: uuid.UUID, step_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    issue = _get(db, JournalIssue, issue_id, "회차")
    step = _get(db, JournalScheduleStep, step_id, "일정 단계")
    if step.issue_id != issue.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정 단계를 찾을 수 없습니다")
    step.completed_at = step.completed_by_user_id = None
    _audit(db, user, "step.reopen", "journal_issue", issue.id, step=step.step_key)
    db.commit()
    return svc.issue_out(db, issue)


class IitpBody(BaseModel):
    confirmed: bool
    note: str | None = None


@router.post("/issues/{issue_id}/iitp")
def set_iitp(issue_id: uuid.UUID, payload: IitpBody, db: Session = Depends(get_db), user: User = Depends(decider)):
    """IITP 공식 확인 여부는 내부 확정과 별개로 승인권자·관리자가 실제 확인한 뒤에만 기록한다."""
    issue = _get(db, JournalIssue, issue_id, "회차")
    issue.iitp_confirmed = payload.confirmed
    issue.iitp_note = payload.note
    issue.iitp_confirmed_by_user_id = user.id if payload.confirmed else None
    issue.iitp_confirmed_at = svc.now() if payload.confirmed else None
    _audit(db, user, "issue.iitp", "journal_issue", issue.id, confirmed=payload.confirmed)
    db.commit()
    return svc.issue_out(db, issue)


@router.post("/issues/{issue_id}/publish")
def record_publication(issue_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(decider)):
    """발간 사실을 내부 이력으로 기록한다(외부 업로드·발송은 하지 않는다). 확정 발간본 출력이 있어야 한다."""
    issue = _get(db, JournalIssue, issue_id, "회차")
    final = db.scalar(select(JournalExport).where(JournalExport.issue_id == issue.id, JournalExport.is_final.is_(True), JournalExport.status == "success"))
    if final is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "확정 발간본(DOCX/PDF)이 없어 발간 기록을 남길 수 없습니다")
    issue.status, issue.published_at = "published", svc.today()
    _audit(db, user, "issue.publish_record", "journal_issue", issue.id)
    db.commit()
    return svc.issue_out(db, issue)


@router.get("/dashboard")
def dashboard(year: int | None = None, mine: bool = False, db: Session = Depends(get_db), user: User = Depends(editor)):
    return svc.dashboard(db, year, user.id if mine else None)


# ---------------------------------------------------------------- 전문가 ----
class ExpertIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    affiliation: str = Field(min_length=1, max_length=200)
    department: str | None = None
    position_title: str | None = None
    fields: list[str] = []
    research_summary: str | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = None
    notes: str | None = None
    is_synthetic: bool = False


@router.get("/experts")
def list_experts(q: str | None = None, field: str | None = None, db: Session = Depends(get_db), _: User = Depends(editor)):
    return svc.search_experts(db, q, field)


@router.post("/experts", status_code=status.HTTP_201_CREATED)
def create_expert(payload: ExpertIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    dup = svc.find_duplicate_expert(db, payload.name, payload.affiliation, payload.email)
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"message": "이미 등록된 전문가입니다(성명·소속 또는 이메일 동일)", "existing_id": str(dup.id),
                                                              "existing_code": dup.expert_code})
    e = JournalExpert(
        expert_code=svc.next_expert_code(db), name=payload.name.strip(), affiliation=payload.affiliation.strip(), department=payload.department,
        position_title=payload.position_title, fields_json=json.dumps(payload.fields, ensure_ascii=False), research_summary=payload.research_summary,
        email=payload.email, phone=payload.phone, notes=payload.notes, is_synthetic=payload.is_synthetic, created_by_user_id=user.id,
    )
    db.add(e)
    db.flush()
    _audit(db, user, "expert.create", "journal_expert", e.id)
    db.commit()
    return svc.expert_out(db, e)


@router.get("/experts/{expert_id}")
def get_expert(expert_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = _get(db, JournalExpert, expert_id, "전문가")
    _audit(db, user, "expert.view", "journal_expert", e.id)  # 개인정보 조회 이력
    db.commit()
    return svc.expert_out(db, e)


class ExpertPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    affiliation: str | None = Field(default=None, min_length=1)
    department: str | None = None
    position_title: str | None = None
    fields: list[str] | None = None
    research_summary: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


@router.patch("/experts/{expert_id}")
def patch_expert(expert_id: uuid.UUID, payload: ExpertPatch, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = _get(db, JournalExpert, expert_id, "전문가")
    if e.anonymized:
        raise HTTPException(status.HTTP_409_CONFLICT, "비식별 처리된 전문가는 수정할 수 없습니다")
    data = payload.model_dump(exclude_unset=True)
    name, aff, email = data.get("name", e.name), data.get("affiliation", e.affiliation), data.get("email", e.email)
    dup = svc.find_duplicate_expert(db, name, aff, email, exclude=e.id)
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"message": "같은 전문가가 이미 등록되어 있습니다", "existing_id": str(dup.id)})
    for key, val in data.items():
        if key == "fields":
            e.fields_json = json.dumps(val, ensure_ascii=False)
        else:
            setattr(e, key, val)
    _audit(db, user, "expert.update", "journal_expert", e.id, fields=sorted(data))
    db.commit()
    return svc.expert_out(db, e)


class ConsentBody(BaseModel):
    consent_status: Literal["none", "agreed", "withdrawn"]
    note: str | None = None


@router.post("/experts/{expert_id}/consent")
def set_consent(expert_id: uuid.UUID, payload: ConsentBody, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = _get(db, JournalExpert, expert_id, "전문가")
    e.consent_status, e.consent_note = payload.consent_status, payload.note
    e.consent_at = svc.now() if payload.consent_status == "agreed" else e.consent_at
    cfg = svc.get_settings(db)
    if payload.consent_status == "agreed" and cfg.get("retention_months"):  # 보존 기간이 설정된 경우에만 만료일을 계산한다(월 단위 30일 근사)
        e.retention_until = svc.today() + timedelta(days=30 * int(cfg["retention_months"]))
    _audit(db, user, "expert.consent", "journal_expert", e.id, status=payload.consent_status)
    db.commit()
    return svc.expert_out(db, e)


@router.post("/experts/{expert_id}/anonymize")
def anonymize_expert(expert_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """보존 기간 만료·동의 철회 시 개인정보를 지운다. 원고·심의 이력은 유지하되 연락처·소속·연구 소개를 비식별 처리한다."""
    e = _get(db, JournalExpert, expert_id, "전문가")
    e.name, e.affiliation, e.department, e.position_title = f"(비식별 {e.expert_code})", "(비식별)", None, None
    e.email = e.phone = e.research_summary = e.notes = None
    e.fields_json = "[]"
    e.anonymized = True
    if e.user_id:
        u = db.get(User, e.user_id)
        if u is not None:
            u.is_active = False
    _audit(db, user, "expert.anonymize", "journal_expert", e.id)
    db.commit()
    return svc.expert_out(db, e)


class AccountIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    expert_id: uuid.UUID | None = None


def _create_account(db: Session, payload: AccountIn, role: UserRole, admin: User) -> User:
    if db.scalar(select(User.id).where(User.email == payload.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 이메일입니다")
    u = User(email=payload.email.lower(), password_hash=hash_password(payload.password), display_name=payload.display_name, role=role,
             job_title="외부 전문가")
    db.add(u)
    db.flush()
    _audit(db, admin, "account.create", "user", u.id, role=role.value)
    return u


@router.post("/accounts/author", status_code=status.HTTP_201_CREATED)
def create_author_account(payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """외부 저자 포털 계정(관리자 전용). 전문가 레코드와 연결해야 자신의 의뢰·원고만 볼 수 있다."""
    if payload.expert_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "연결할 전문가(expert_id)가 필요합니다")
    expert = _get(db, JournalExpert, payload.expert_id, "전문가")
    if expert.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 포털 계정이 연결된 전문가입니다")
    u = _create_account(db, payload, UserRole.AUTHOR, user)
    expert.user_id = u.id
    db.commit()
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name, "role": u.role.value, "expert_id": str(expert.id)}


@router.post("/accounts/reviewer", status_code=status.HTTP_201_CREATED)
def create_reviewer_account(payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    u = _create_account(db, payload, UserRole.EXT_REVIEWER, user)
    db.commit()
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name, "role": u.role.value}


@router.get("/reviewer-candidates")
def reviewer_candidates(db: Session = Depends(get_db), _: User = Depends(editor)):
    users = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_([UserRole.REVIEWER, UserRole.EXT_REVIEWER]))
                       .order_by(User.display_name)).all()
    return [{"id": str(u.id), "display_name": u.display_name, "role": u.role.value, "external": u.role == UserRole.EXT_REVIEWER} for u in users]


# ---------------------------------------------------------------- 의뢰 ----
class CommissionIn(BaseModel):
    issue_id: uuid.UUID
    expert_id: uuid.UUID
    topic: str = Field(min_length=1, max_length=500)
    purpose: str | None = None
    outline: str | None = None
    length_spec: str | None = None
    format_spec: str | None = None
    due_date: date | None = None
    delivery_method: str | None = None
    contact_info: str | None = None
    candidate_id: uuid.UUID | None = None


@router.get("/commissions")
def list_commissions(issue_id: uuid.UUID | None = None, status_: str | None = Query(default=None, alias="status"),
                     db: Session = Depends(get_db), _: User = Depends(editor)):
    stmt = select(JournalCommission).order_by(JournalCommission.created_at.desc())
    if issue_id:
        stmt = stmt.where(JournalCommission.issue_id == issue_id)
    if status_:
        stmt = stmt.where(JournalCommission.status == status_)
    return [svc.commission_out(db, c) for c in db.scalars(stmt).all()]


@router.post("/commissions", status_code=status.HTTP_201_CREATED)
def create_commission(payload: CommissionIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    issue = _get(db, JournalIssue, payload.issue_id, "회차")
    expert = _get(db, JournalExpert, payload.expert_id, "전문가")
    if expert.anonymized:
        raise HTTPException(status.HTTP_409_CONFLICT, "비식별 처리된 전문가에게는 의뢰할 수 없습니다")
    if payload.candidate_id and db.get(Candidate, payload.candidate_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "후보주제를 찾을 수 없습니다")
    c = JournalCommission(created_by_user_id=user.id, **payload.model_dump())
    db.add(c)
    db.flush()
    svc.log_commission(db, c, "created", user.id, note="후보주제에서 가져옴(AI 추천 주제는 IITP 확정 주제가 아님)" if payload.candidate_id else None)
    if issue.status == "planning":
        issue.status = "recruiting"
    _audit(db, user, "commission.create", "journal_commission", c.id)
    db.commit()
    return svc.commission_out(db, c, include_events=True)


@router.get("/commissions/{cid}")
def get_commission(cid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(editor)):
    return svc.commission_out(db, _get(db, JournalCommission, cid, "의뢰"), include_events=True)


class CommissionPatch(BaseModel):
    topic: str | None = Field(default=None, min_length=1)
    purpose: str | None = None
    outline: str | None = None
    length_spec: str | None = None
    format_spec: str | None = None
    due_date: date | None = None
    delivery_method: str | None = None
    contact_info: str | None = None


@router.patch("/commissions/{cid}")
def patch_commission(cid: uuid.UUID, payload: CommissionPatch, db: Session = Depends(get_db), user: User = Depends(editor)):
    c = _get(db, JournalCommission, cid, "의뢰")
    data = payload.model_dump(exclude_unset=True)
    old_due = c.due_date
    for k, v in data.items():
        setattr(c, k, v)
    if "due_date" in data and old_due != c.due_date:
        svc.log_commission(db, c, "due_changed", user.id, note=f"{old_due} → {c.due_date}")
    _audit(db, user, "commission.update", "journal_commission", c.id, fields=sorted(data))
    db.commit()
    return svc.commission_out(db, c, include_events=True)


@router.get("/commissions/{cid}/mail-preview")
def mail_preview(cid: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(editor)):
    c = _get(db, JournalCommission, cid, "의뢰")
    draft = svc.mail_draft(db, c)
    return {**draft, "saved": {"subject": c.mail_subject, "body": c.mail_body, "status": c.mail_status}, "notice": "미리보기입니다 — 실제로 발송되지 않습니다"}


class MailSave(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    queue: bool = False


@router.put("/commissions/{cid}/mail")
def save_mail(cid: uuid.UUID, payload: MailSave, db: Session = Depends(get_db), user: User = Depends(editor)):
    """안내 메일 임시저장 또는 '발송 대기' 표시. 이 단계에서는 어떤 경우에도 외부로 발송하지 않는다."""
    c = _get(db, JournalCommission, cid, "의뢰")
    c.mail_subject, c.mail_body = payload.subject, payload.body
    c.mail_status = "pending_send" if payload.queue else "draft"
    if payload.queue and c.status == "draft":
        svc.change_commission_status(db, c, "ready", user.id, "안내 메일 발송 대기로 표시(실제 발송 없음)")
    svc.log_commission(db, c, "mail_saved", user.id, note="발송 대기" if payload.queue else "임시저장")
    db.commit()
    return svc.commission_out(db, c, include_events=True)


class StatusBody(BaseModel):
    status: Literal["draft", "ready", "requested", "accepted", "declined", "no_response"]
    note: str | None = None


@router.post("/commissions/{cid}/status")
def commission_status(cid: uuid.UUID, payload: StatusBody, db: Session = Depends(get_db), user: User = Depends(editor)):
    c = _get(db, JournalCommission, cid, "의뢰")
    svc.change_commission_status(db, c, payload.status, user.id, payload.note)
    _audit(db, user, "commission.status", "journal_commission", c.id, to=payload.status)
    db.commit()
    return svc.commission_out(db, c, include_events=True)


# ---------------------------------------------------------------- 원고 ----
def _ms(db: Session, mid: uuid.UUID) -> JournalManuscript:
    return _get(db, JournalManuscript, mid, "원고")


@router.get("/manuscripts")
def list_manuscripts(issue_id: uuid.UUID | None = None, status_: str | None = Query(default=None, alias="status"),
                     db: Session = Depends(get_db), _: User = Depends(editor)):
    stmt = select(JournalManuscript).order_by(JournalManuscript.created_at.desc())
    if issue_id:
        stmt = stmt.where(JournalManuscript.issue_id == issue_id)
    if status_:
        stmt = stmt.where(JournalManuscript.status == status_)
    out = []
    for m in db.scalars(stmt).all():
        o = svc.manuscript_out(db, m)
        out.append({k: o[k] for k in ("id", "issue_label", "title", "expert_name", "status", "status_label", "format_status", "version_count",
                                      "open_comment_count", "proof_confirmed")})
    return out


@router.get("/manuscripts/{mid}")
def get_manuscript(mid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    _audit(db, user, "manuscript.view", "journal_manuscript", ms.id)
    db.commit()
    return svc.manuscript_out(db, ms)


class ManuscriptPatch(BaseModel):
    lock_version: int
    title: str | None = Field(default=None, min_length=1)
    title_en: str | None = None
    summary: str | None = None
    references_text: str | None = None
    copyright_confirmed: bool | None = None
    third_party_note: str | None = None


@router.patch("/manuscripts/{mid}")
def patch_manuscript(mid: uuid.UUID, payload: ManuscriptPatch, db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    if ms.lock_version != payload.lock_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "다른 사용자가 먼저 수정했습니다. 최신 내용을 다시 불러오세요.")
    data = payload.model_dump(exclude_unset=True, exclude={"lock_version"})
    for k, v in data.items():
        setattr(ms, k, v)
    ms.lock_version += 1
    _audit(db, user, "manuscript.update", "journal_manuscript", ms.id, fields=sorted(data))
    db.commit()
    return svc.manuscript_out(db, ms)


def _store_version(db: Session, ms: JournalManuscript, user: User, file: UploadFile, kind: str, note: str | None) -> JournalVersion:
    cfg, data, limit = _upload(db, file, "manuscript_ext")
    try:
        ver = svc.submit_version(db, ms, user, file.filename or "manuscript", data, kind, note)
    except journal_files.UploadRejected as exc:
        _audit(db, user, "upload.rejected", "journal_manuscript", ms.id, reason=str(exc), file=file.filename)
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return ver


@router.post("/manuscripts/{mid}/versions", status_code=status.HTTP_201_CREATED)
def upload_version(mid: uuid.UUID, file: UploadFile = File(...), kind: Literal["submission", "revision", "proofread"] = Form("proofread"),
                   note: str | None = Form(None), checklist_json: str | None = Form(None),
                   db: Session = Depends(get_db), user: User = Depends(editor)):
    """편집 담당자가 파일을 올린다(교정본, 또는 이메일로 받은 제출본·수정본의 대리 접수). 기존 파일은 덮어쓰지 않는다."""
    ms = _ms(db, mid)
    if kind == "proofread" and ms.status != "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "교정본은 게재 확정된 원고에만 올릴 수 있습니다")
    if kind == "revision" and ms.status != "revision_requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "수정 요청 상태에서만 수정본을 접수할 수 있습니다")
    if kind == "submission" and ms.status not in ("received", "format_fix_needed") and ms.version_count > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 접수된 원고입니다 — 수정본은 수정 요청 이후 접수하세요")
    ver = _store_version(db, ms, user, file, kind, note)
    if kind == "proofread":
        ver.proof_checklist_json = checklist_json
        ms.proof_version_id = ver.id
        ms.proof_confirmed_at = ms.proof_confirmed_by_user_id = None  # 새 교정본이 올라오면 최종 교정 확인을 다시 받아야 한다
    else:
        svc.apply_submission_status(ms, ver)
        if kind == "revision":
            _link_replies(db, ms, ver)
    _audit(db, user, "version.upload", "journal_manuscript", ms.id, kind=kind, version=ver.version_no)
    db.commit()
    return svc.manuscript_out(db, ms)


def _link_replies(db: Session, ms: JournalManuscript, ver: JournalVersion) -> None:
    for c in db.scalars(select(JournalComment).where(JournalComment.manuscript_id == ms.id, JournalComment.status == "answered",
                                                     JournalComment.reply_version_id.is_(None))).all():
        c.reply_version_id = ver.id


@router.get("/manuscripts/{mid}/versions/{vid}/download")
def download_version(mid: uuid.UUID, vid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    ver = _get(db, JournalVersion, vid, "버전")
    if ver.manuscript_id != ms.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "버전을 찾을 수 없습니다")
    _audit(db, user, "version.download", "journal_manuscript", ms.id, version=ver.version_no)
    db.commit()
    return _file_response(ver.file_path, ver.file_name, ver.mime)


def _file_response(path: str, name: str, mime: str | None) -> Response:
    try:
        data = journal_files.read(path)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")
    from urllib.parse import quote

    return Response(content=data, media_type=mime or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "X-Content-Type-Options": "nosniff"})


class FormatReview(BaseModel):
    result: Literal["ok", "needs_fix"]
    note: str | None = None


@router.post("/manuscripts/{mid}/format-review")
def format_review(mid: uuid.UUID, payload: FormatReview, db: Session = Depends(get_db), user: User = Depends(editor)):
    """형식 검토 결과 확정(내용의 학술·기술 타당성 검토와는 별개 상태)."""
    ms = _ms(db, mid)
    if ms.status not in ("received", "format_fix_needed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "접수 완료 또는 형식 보완 필요 상태에서만 형식 검토를 확정할 수 있습니다")
    ms.format_status = payload.result
    if payload.result == "needs_fix":
        if ms.status == "received":
            svc.set_status(ms, "format_fix_needed")
        if payload.note:
            db.add(JournalComment(manuscript_id=ms.id, author_user_id=user.id, kind="format", scope="doc", text=payload.note, requires_revision=True))
    else:
        if ms.status == "format_fix_needed":
            svc.set_status(ms, "received")
        svc.set_status(ms, "review_pending")
    _audit(db, user, "manuscript.format_review", "journal_manuscript", ms.id, result=payload.result)
    db.commit()
    return svc.manuscript_out(db, ms)


class AssignIn(BaseModel):
    reviewer_user_id: uuid.UUID
    round: int = Field(default=1, ge=1, le=3)
    role_kind: Literal["reviewer", "committee"] = "reviewer"
    due_date: date | None = None
    conflict_declared: bool = False
    conflict_note: str | None = None
    confirm_conflict: bool = False


@router.post("/manuscripts/{mid}/assignments", status_code=status.HTTP_201_CREATED)
def assign_reviewer(mid: uuid.UUID, payload: AssignIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    reviewer = _get(db, User, payload.reviewer_user_id, "검토자")
    if reviewer.role not in (UserRole.REVIEWER, UserRole.EXT_REVIEWER, UserRole.APPROVER):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "검토자 권한이 있는 사용자만 배정할 수 있습니다")
    if ms.status not in ("review_pending", "in_review", "revision_received", "deliberated"):
        raise HTTPException(status.HTTP_409_CONFLICT, "형식 검토를 마친 원고에만 검토자를 배정할 수 있습니다")
    expert = db.get(JournalExpert, ms.expert_id)
    warnings = []
    if expert is not None and expert.user_id == reviewer.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "저자 본인을 검토자로 배정할 수 없습니다")
    linked = db.scalar(select(JournalExpert).where(JournalExpert.user_id == reviewer.id))
    if linked is not None and expert is not None and linked.affiliation.strip().lower() == expert.affiliation.strip().lower():
        warnings.append("검토자와 저자의 소속이 같습니다 — 이해상충 여부를 확인하세요")
    if payload.conflict_declared:
        warnings.append("이해상충이 확인된 검토자입니다")
    if db.scalar(select(JournalAssignment.id).where(JournalAssignment.manuscript_id == ms.id, JournalAssignment.reviewer_user_id == reviewer.id,
                                                    JournalAssignment.round == payload.round)):
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 회차에 이미 배정된 검토자입니다")
    if warnings and not payload.confirm_conflict:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"message": "이해상충 경고가 있습니다 — 확인 후 다시 배정하세요(confirm_conflict)",
                                                              "warnings": warnings})
    a = JournalAssignment(
        manuscript_id=ms.id, reviewer_user_id=reviewer.id, round=payload.round, role_kind=payload.role_kind, due_date=payload.due_date,
        conflict_declared=payload.conflict_declared, conflict_checked=False, conflict_note=payload.conflict_note,  # 이해상충 확인은 검토자 본인이 해야 한다
        assigned_by_user_id=user.id,
    )
    db.add(a)
    if ms.status in ("review_pending", "revision_received"):
        svc.set_status(ms, "in_review")
        ms.content_status = "in_review"
    _audit(db, user, "assignment.create", "journal_manuscript", ms.id, reviewer=str(reviewer.id), round=payload.round, warnings=warnings)
    db.commit()
    out = svc.assignment_out(db, a)
    out["warnings"] = warnings
    return out


class CommentIn(BaseModel):
    scope: Literal["doc", "paragraph", "table", "figure"] = "doc"
    anchor_text: str | None = None
    anchor_index: int | None = None
    text: str = Field(min_length=1)
    requires_revision: bool = True
    kind: Literal["review", "format", "deliberation"] = "review"


@router.post("/manuscripts/{mid}/comments", status_code=status.HTTP_201_CREATED)
def add_comment(mid: uuid.UUID, payload: CommentIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
    c = JournalComment(manuscript_id=ms.id, version_id=last.id if last else None, author_user_id=user.id, **payload.model_dump())
    db.add(c)
    db.flush()
    _audit(db, user, "comment.create", "journal_manuscript", ms.id, scope=payload.scope)
    db.commit()
    return svc.comment_out(db, c, anonymize=False)


@router.post("/manuscripts/{mid}/comments/{cid}/resolve")
def resolve_comment(mid: uuid.UUID, cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    c = _get(db, JournalComment, cid, "의견")
    if c.manuscript_id != mid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "의견을 찾을 수 없습니다")
    c.status, c.resolved_by_user_id, c.resolved_at = "resolved", user.id, svc.now()
    _audit(db, user, "comment.resolve", "journal_manuscript", mid)
    db.commit()
    return svc.comment_out(db, c, anonymize=False)


class RevisionRequest(BaseModel):
    note: str | None = None


@router.post("/manuscripts/{mid}/request-revision")
def request_revision(mid: uuid.UUID, payload: RevisionRequest, db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    open_comments = db.scalar(select(func.count()).select_from(JournalComment).where(
        JournalComment.manuscript_id == ms.id, JournalComment.status == "open", JournalComment.requires_revision.is_(True))) or 0
    if not open_comments and not (payload.note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "수정 요청에는 미해결 검토 의견 또는 요청 내용이 필요합니다")
    if (payload.note or "").strip():
        last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
        db.add(JournalComment(manuscript_id=ms.id, version_id=last.id if last else None, author_user_id=user.id, kind="review", scope="doc",
                              text=payload.note, requires_revision=True))
    svc.set_status(ms, "revision_requested")
    _audit(db, user, "manuscript.request_revision", "journal_manuscript", ms.id, open_comments=open_comments)
    db.commit()
    return svc.manuscript_out(db, ms)


@router.post("/manuscripts/{mid}/deliberate")
def deliberate(mid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    """검토를 마치고 심의 대기 상태로 전환(심의 결과 확정은 승인권자 결정 API에서)."""
    ms = _ms(db, mid)
    pending = db.scalars(select(JournalAssignment).where(JournalAssignment.manuscript_id == ms.id, JournalAssignment.status != "completed")).all()
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, f"검토가 끝나지 않은 배정 {len(pending)}건이 있습니다")
    if not db.scalar(select(JournalAssignment.id).where(JournalAssignment.manuscript_id == ms.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "검토자 배정·검토 이력이 없어 심의로 넘길 수 없습니다")
    svc.set_status(ms, "deliberated")
    ms.content_status = "done"
    _audit(db, user, "manuscript.deliberate", "journal_manuscript", ms.id)
    db.commit()
    return svc.manuscript_out(db, ms)


class DecisionIn(BaseModel):
    outcome: str
    note: str | None = None


@router.post("/manuscripts/{mid}/decision")
def decide(mid: uuid.UUID, payload: DecisionIn, db: Session = Depends(get_db), user: User = Depends(decider)):
    """심의 결과 확정. 자동 점수로 정하지 않고 승인권자·관리자가 결과 구분(관리자 설정)을 선택해 기록한다."""
    ms = _ms(db, mid)
    cfg = svc.get_settings(db)
    outcome = next((o for o in cfg["decision_outcomes"] if o["key"] == payload.outcome), None)
    if outcome is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "알 수 없는 심의 결과입니다")
    if ms.status != "deliberated":
        raise HTTPException(status.HTTP_409_CONFLICT, "심의 완료 상태에서만 결과를 확정할 수 있습니다")
    round_no = (db.scalar(select(func.max(JournalDecision.round)).where(JournalDecision.manuscript_id == ms.id)) or 0) + 1
    last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
    effect = outcome["effect"]
    final = effect in ("accept", "hold", "reject")
    dec = JournalDecision(manuscript_id=ms.id, version_id=last.id if last else None, round=round_no, outcome=payload.outcome, note=payload.note,
                          decided_by_user_id=user.id, is_final=final)
    db.add(dec)
    if effect == "accept":
        if ms.format_status == "needs_fix":
            raise HTTPException(status.HTTP_409_CONFLICT, "형식 보완이 끝나지 않은 원고는 게재 확정할 수 없습니다")
        open_c = db.scalar(select(func.count()).select_from(JournalComment).where(
            JournalComment.manuscript_id == ms.id, JournalComment.status != "resolved", JournalComment.requires_revision.is_(True))) or 0
        if open_c:
            raise HTTPException(status.HTTP_409_CONFLICT, f"해결되지 않은 수정 요청 의견 {open_c}건이 있습니다 — 해결 처리 후 게재 확정하세요")
        svc.set_status(ms, "accepted")
        ms.accepted_version_id = last.id if last else None
    elif effect == "hold":
        svc.set_status(ms, "held")
    elif effect == "reject":
        svc.set_status(ms, "rejected")
    else:  # revise: 수정 요청으로 되돌린다(최종 결정 아님)
        svc.set_status(ms, "revision_requested")
        if (payload.note or "").strip():
            db.add(JournalComment(manuscript_id=ms.id, version_id=last.id if last else None, author_user_id=user.id, kind="deliberation", scope="doc",
                                  text=payload.note, requires_revision=True))
    _audit(db, user, "manuscript.decision", "journal_manuscript", ms.id, outcome=payload.outcome, final=final)
    db.commit()
    return svc.manuscript_out(db, ms)


@router.get("/manuscripts/{mid}/compare")
def compare(mid: uuid.UUID, from_version: int = Query(alias="from"), to_version: int = Query(alias="to"),
            db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    old = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id, JournalVersion.version_no == from_version))
    new = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id, JournalVersion.version_no == to_version))
    if old is None or new is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "비교할 버전을 찾을 수 없습니다")
    return _compare(db, ms, old, new, anonymize=False)


def _compare(db: Session, ms: JournalManuscript, old: JournalVersion, new: JournalVersion, *, anonymize: bool) -> dict:
    old_ex = journal_docx.extract(journal_files.read(old.file_path), journal_files.ext_of(old.file_name))
    new_ex = journal_docx.extract(journal_files.read(new.file_path), journal_files.ext_of(new.file_name))
    cmp = journal_docx.compare_versions(old_ex, new_ex)
    comments = [svc.comment_out(db, c, anonymize=anonymize) for c in db.scalars(select(JournalComment).where(
        JournalComment.manuscript_id == ms.id, JournalComment.created_at <= new.created_at).order_by(JournalComment.created_at)).all()]
    mapped = journal_docx.map_comments(comments, old_ex.get("paragraphs", []), new_ex.get("paragraphs", []))
    return {"from_version": old.version_no, "to_version": new.version_no, **cmp, "comment_mapping": mapped,
            "notice": "자동 비교는 문단 텍스트 기준입니다. 수정되지 않은 의견을 수정 완료로 표시하지 않습니다 — 해결 처리는 담당자가 확인 후 합니다."}


# ---------------------------------------------------------------- 교정·표절·첨부 ----
class ProofConfirm(BaseModel):
    checklist: dict[str, bool]


PROOF_ITEMS = ["source", "figure_table_numbers", "references", "abbreviations", "language"]


@router.post("/manuscripts/{mid}/proof/confirm")
def confirm_proof(mid: uuid.UUID, payload: ProofConfirm, db: Session = Depends(get_db), user: User = Depends(editor)):
    """최종 교정 확인 — 원문 출처·그림/표 번호·참고문헌·약어·문장 오류 점검표를 모두 확인해야 한다."""
    ms = _ms(db, mid)
    if ms.status != "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "게재 확정된 원고만 최종 교정 확인을 할 수 있습니다")
    missing = [k for k in PROOF_ITEMS if not payload.checklist.get(k)]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"점검표 미확인 항목: {', '.join(missing)}")
    ver = db.get(JournalVersion, ms.proof_version_id) if ms.proof_version_id else None
    if ver is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "교정본이 올라와 있지 않습니다 — 교정본을 먼저 올리세요(교정 없이 확정하려면 확정본을 교정본으로 올려도 됩니다)")
    ver.proof_checklist_json = json.dumps(payload.checklist, ensure_ascii=False)
    ms.proof_confirmed_at, ms.proof_confirmed_by_user_id = svc.now(), user.id
    _audit(db, user, "manuscript.proof_confirm", "journal_manuscript", ms.id, version=ver.version_no)
    db.commit()
    return svc.manuscript_out(db, ms)


@router.post("/manuscripts/{mid}/plagiarism", status_code=status.HTTP_201_CREATED)
def upload_plagiarism(mid: uuid.UUID, file: UploadFile = File(...), service_name: str | None = Form(None), similarity_pct: float | None = Form(None),
                      note: str | None = Form(None), db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    cfg, data, limit = _upload(db, file, "attachment_ext")
    try:
        journal_files.scan_upload(file.filename or "result", data, cfg["attachment_ext"], limit)
    except journal_files.UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    path, digest = journal_files.store("plagiarism", ms.id, file.filename or "result", data)
    last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
    p = JournalPlagiarism(manuscript_id=ms.id, version_id=last.id if last else None, service_name=service_name, file_name=journal_files.safe_name(file.filename or "result"),
                          file_path=path, sha256=digest, similarity_pct=similarity_pct, note=note, uploaded_by_user_id=user.id)
    db.add(p)
    _audit(db, user, "plagiarism.upload", "journal_manuscript", ms.id)
    db.commit()
    return svc.manuscript_out(db, ms)["plagiarism"][-1]


@router.post("/manuscripts/{mid}/plagiarism/{pid}/confirm")
def confirm_plagiarism(mid: uuid.UUID, pid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = _get(db, JournalPlagiarism, pid, "표절검사 결과")
    if p.manuscript_id != mid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "표절검사 결과를 찾을 수 없습니다")
    p.status, p.confirmed_by_user_id, p.confirmed_at = "confirmed", user.id, svc.now()
    _audit(db, user, "plagiarism.confirm", "journal_manuscript", mid)
    db.commit()
    return {"id": str(p.id), "status": p.status}


@router.post("/manuscripts/{mid}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(mid: uuid.UUID, doc_type: str = Form(...), file: UploadFile = File(...), note: str | None = Form(None),
                      db: Session = Depends(get_db), user: User = Depends(editor)):
    ms = _ms(db, mid)
    return _save_attachment(db, ms, user, doc_type, file, note)


def _save_attachment(db: Session, ms: JournalManuscript, user: User, doc_type: str, file: UploadFile, note: str | None) -> dict:
    cfg, data, limit = _upload(db, file, "attachment_ext")
    try:
        scan = journal_files.scan_upload(file.filename or "attachment", data, cfg["attachment_ext"], limit)
    except journal_files.UploadRejected as exc:
        _audit(db, user, "upload.rejected", "journal_manuscript", ms.id, reason=str(exc), file=file.filename)
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    path, digest = journal_files.store("attachments", ms.id, file.filename or "attachment", data)
    last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
    a = JournalAttachment(manuscript_id=ms.id, version_id=last.id if last else None, doc_type=doc_type, file_name=journal_files.safe_name(file.filename or "attachment"),
                          file_path=path, file_size=len(data), sha256=digest, scan_json=json.dumps(scan, ensure_ascii=False), note=note,
                          uploaded_by_user_id=user.id)
    db.add(a)
    ms.lock_version += 1
    _audit(db, user, "attachment.upload", "journal_manuscript", ms.id, doc_type=doc_type)
    db.commit()
    return {"id": str(a.id), "doc_type": a.doc_type, "file_name": a.file_name, "sha256": a.sha256}


@router.get("/manuscripts/{mid}/attachments/{aid}/download")
def download_attachment(mid: uuid.UUID, aid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    a = _get(db, JournalAttachment, aid, "첨부")
    if a.manuscript_id != mid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "첨부를 찾을 수 없습니다")
    _audit(db, user, "attachment.download", "journal_manuscript", mid)
    db.commit()
    return _file_response(a.file_path, a.file_name, None)


# ---------------------------------------------------------------- 회차 구성·발간본 ----
class ItemsIn(BaseModel):
    manuscript_ids: list[uuid.UUID]


@router.put("/issues/{issue_id}/items")
def set_items(issue_id: uuid.UUID, payload: ItemsIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    """게재 확정 원고를 회차에 배치하고 순서를 정한다. 교정본이 확정되어 있으면 교정본, 아니면 게재 확정 시점의 버전을 쓴다."""
    issue = _get(db, JournalIssue, issue_id, "회차")
    if issue.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "발간 기록된 회차는 구성을 바꿀 수 없습니다")
    if len(set(payload.manuscript_ids)) != len(payload.manuscript_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "같은 원고가 중복되었습니다")
    for it in db.scalars(select(JournalIssueItem).where(JournalIssueItem.issue_id == issue.id)).all():
        db.delete(it)
    db.flush()
    for pos, mid in enumerate(payload.manuscript_ids, start=1):
        ms = _get(db, JournalManuscript, mid, "원고")
        if ms.status != "accepted":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{ms.title[:30]}'은(는) 게재 확정되지 않아 배치할 수 없습니다")
        ver_id = ms.proof_version_id if (ms.proof_confirmed_at and ms.proof_version_id) else ms.accepted_version_id
        if ver_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{ms.title[:30]}'의 게재 버전을 찾을 수 없습니다")
        db.add(JournalIssueItem(issue_id=issue.id, manuscript_id=ms.id, version_id=ver_id, position=pos))
    if issue.status in ("planning", "recruiting", "receiving", "reviewing"):
        issue.status = "editing"
    _audit(db, user, "issue.items", "journal_issue", issue.id, count=len(payload.manuscript_ids))
    db.commit()
    return get_issue(issue_id, db, user)


class ExportIn(BaseModel):
    file_format: Literal["docx", "pdf"]
    final: bool = False


@router.post("/issues/{issue_id}/exports", status_code=status.HTTP_201_CREATED)
def create_export(issue_id: uuid.UUID, payload: ExportIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    issue = _get(db, JournalIssue, issue_id, "회차")
    items = list(db.scalars(select(JournalIssueItem).where(JournalIssueItem.issue_id == issue.id).order_by(JournalIssueItem.position)).all())
    if not items:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "회차에 배치된 게재 원고가 없습니다")
    if payload.final:
        if user.role not in svc.DECIDER_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "확정 발간본은 승인권자·관리자만 만들 수 있습니다")
        blocking = svc.export_blocking(svc.export_preflight(db, issue, items))
        if blocking:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"message": "필수 점검을 통과하지 못해 확정 발간본을 만들 수 없습니다", "blocking": blocking})
    try:
        exp = svc.generate_export(db, issue, file_format=payload.file_format, user_id=user.id, final=payload.final)
    except svc.ExportInProgressError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    _audit(db, user, "export.create", "journal_issue", issue.id, format=payload.file_format, final=payload.final, status=exp.status)
    db.commit()
    return svc.export_out(exp)


@router.get("/issues/{issue_id}/exports/{eid}/download")
def download_export(issue_id: uuid.UUID, eid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = _get(db, JournalExport, eid, "발간본")
    if e.issue_id != issue_id or e.status != "success":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "발간본을 찾을 수 없습니다")
    media = "application/pdf" if e.file_format == "pdf" else journal_files.DOCX_MIME
    _audit(db, user, "export.download", "journal_issue", issue_id)
    db.commit()
    return _file_response(e.file_path, e.file_name or "journal", media)
