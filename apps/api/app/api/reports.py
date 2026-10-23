import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.enums import UserRole
from app.models.manuscript import Manuscript
from app.models.report import Report, ReportExport, ReportItem, ReportTemplate
from app.models.user import User
from app.schemas.report import (
    ExportRequest,
    FinalizeRequest,
    PreflightIssue,
    ReorderRequest,
    ReportCreate,
    ReportDetailOut,
    ReportExportOut,
    ReportItemCreate,
    ReportItemOut,
    ReportItemUpdate,
    ReportListItemOut,
    ReportUpdate,
    SummaryItemCreate,
    TemplateConfigPatch,
    TemplateOut,
)
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])
template_router = APIRouter(prefix="/report-templates", tags=["reports"])

PRIVILEGED = (UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)
APPROVERS = (UserRole.ADMIN, UserRole.APPROVER)


def _get_report(db: Session, report_id: uuid.UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다")
    return report


def _assert_can_edit(report: Report, user: User) -> None:
    if report.created_by_user_id != user.id and user.role not in PRIVILEGED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "본인이 만든 보고서만 수정할 수 있습니다")
    if report.status == "final":
        raise HTTPException(status.HTTP_409_CONFLICT, "출력용 확정된 보고서입니다 — 승인권자가 '확정 해제' 후 수정해야 합니다")


def _assert_can_access_files(report: Report, user: User) -> None:
    if report.created_by_user_id != user.id and user.role not in PRIVILEGED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "다른 사용자가 만든 보고서의 출력 파일에는 접근할 수 없습니다")


def _item_out(db: Session, item: ReportItem) -> ReportItemOut:
    ms = db.get(Manuscript, item.manuscript_id) if item.manuscript_id else None
    needs_review = False
    if item.summary_text is not None and ms is not None and item.source_sentence:
        needs_review = report_service._summary_item_block(db, item)["needs_review"]
    return ReportItemOut(
        id=item.id, position=item.position, part_key=item.part_key, heading=item.heading,
        manuscript_id=item.manuscript_id, manuscript_title=ms.title if ms else None,
        manuscript_status=ms.status.value if ms else None, summary_text=item.summary_text,
        source_sentence=item.source_sentence, needs_review=needs_review,
    )


def _detail(db: Session, report: Report) -> ReportDetailOut:
    items = db.scalars(select(ReportItem).where(ReportItem.report_id == report.id).order_by(ReportItem.position)).all()
    snapshot = report_service.build_snapshot(db, report)
    issues = report_service.run_preflight(snapshot)
    return ReportDetailOut(
        **ReportListItemOut.model_validate(report).model_dump(),
        title_en=report.title_en, publish_date=report.publish_date, template_id=report.template_id,
        iitp_confirmed=report.iitp_confirmed, finalize_exception_reason=report.finalize_exception_reason,
        finalized_at=report.finalized_at, items=[_item_out(db, i) for i in items],
        preflight=[PreflightIssue(**i) for i in issues],
        blocking=[PreflightIssue(**i) for i in report_service.blocking_issues(issues)],
    )


@router.get("", response_model=list[ReportListItemOut])
def list_reports(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Report).order_by(Report.updated_at.desc())).all()


@router.post("", response_model=ReportDetailOut, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    template = report_service.get_active_template(db)
    report = Report(
        report_type=payload.report_type, title=payload.title, title_en=payload.title_en, edition_id=payload.edition_id,
        publish_date=payload.publish_date, template_id=template.id, created_by_user_id=user.id,
    )
    db.add(report)
    db.flush()
    log_action(db, actor_user_id=user.id, action="report.create", entity_type="report", entity_id=report.id,
               detail={"type": payload.report_type})
    db.commit()
    db.refresh(report)
    return _detail(db, report)


@router.get("/source-sentences/{manuscript_id}")
def source_sentences(manuscript_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """요약본에 반영할 문장을 고르기 위한 원고 문단 목록(연구원이 직접 선택·편집한다 — AI 요약 아님)."""
    ms = db.get(Manuscript, manuscript_id)
    if ms is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "원고를 찾을 수 없습니다")
    lines = [ln.strip() for ln in (ms.body or "").splitlines() if len(ln.strip()) >= 8]
    return {"manuscript_id": str(ms.id), "title": ms.title, "sentences": lines}


@router.get("/{report_id}", response_model=ReportDetailOut)
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _detail(db, _get_report(db, report_id))


@router.patch("/{report_id}", response_model=ReportDetailOut)
def update_report(report_id: uuid.UUID, payload: ReportUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_edit(report, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(report, field, value)
    report.lock_version += 1
    db.commit()
    db.refresh(report)
    return _detail(db, report)


def _next_position(db: Session, report_id: uuid.UUID) -> int:
    return (db.scalar(select(func.max(ReportItem.position)).where(ReportItem.report_id == report_id)) or 0) + 1


@router.post("/{report_id}/items", response_model=ReportDetailOut, status_code=status.HTTP_201_CREATED)
def add_item(report_id: uuid.UUID, payload: ReportItemCreate, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_edit(report, user)
    if report.report_type == "summary":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "요약본에는 원고 대신 요약 문장을 추가하세요")
    if db.get(Manuscript, payload.manuscript_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "원고를 찾을 수 없습니다")
    if report.report_type == "general" and payload.part_key not in {k for k, _, _ in report_service.GENERAL_PARTS}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "일반호는 지정된 목차 파트에만 원고를 배치할 수 있습니다")
    duplicate = db.scalar(select(ReportItem).where(
        ReportItem.report_id == report.id, ReportItem.manuscript_id == payload.manuscript_id))
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 이 보고서에 배치된 원고입니다")
    db.add(ReportItem(
        report_id=report.id, position=_next_position(db, report.id), part_key=payload.part_key or "free",
        heading=payload.heading, manuscript_id=payload.manuscript_id,
    ))
    report.lock_version += 1
    db.commit()
    return _detail(db, report)


@router.post("/{report_id}/summary-items", response_model=ReportDetailOut, status_code=status.HTTP_201_CREATED)
def add_summary_item(report_id: uuid.UUID, payload: SummaryItemCreate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_edit(report, user)
    if report.report_type != "summary":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "요약본에서만 요약 문장을 추가할 수 있습니다")
    ms = db.get(Manuscript, payload.manuscript_id)
    if ms is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "원고를 찾을 수 없습니다")
    if report_service._norm(payload.source_sentence) not in report_service._norm(ms.body or ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "선택한 문장이 원고 본문에 없습니다")
    db.add(ReportItem(
        report_id=report.id, position=_next_position(db, report.id), part_key=payload.part_key,
        manuscript_id=ms.id, source_sentence=payload.source_sentence.strip(), summary_text=payload.source_sentence.strip(),
    ))
    report.lock_version += 1
    db.commit()
    return _detail(db, report)


@router.patch("/{report_id}/items/{item_id}", response_model=ReportDetailOut)
def update_item(report_id: uuid.UUID, item_id: uuid.UUID, payload: ReportItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_edit(report, user)
    item = db.get(ReportItem, item_id)
    if item is None or item.report_id != report.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "항목을 찾을 수 없습니다")
    data = payload.model_dump(exclude_unset=True)
    if "summary_text" in data and item.summary_text is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "요약 항목만 요약문을 수정할 수 있습니다")
    for field, value in data.items():
        setattr(item, field, value)
    report.lock_version += 1
    db.commit()
    return _detail(db, report)


@router.delete("/{report_id}/items/{item_id}", response_model=ReportDetailOut)
def delete_item(report_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_edit(report, user)
    item = db.get(ReportItem, item_id)
    if item is None or item.report_id != report.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "항목을 찾을 수 없습니다")
    db.delete(item)
    report.lock_version += 1
    db.commit()
    return _detail(db, report)


@router.post("/{report_id}/items/reorder", response_model=ReportDetailOut)
def reorder_items(report_id: uuid.UUID, payload: ReorderRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_edit(report, user)
    items = {i.id: i for i in db.scalars(select(ReportItem).where(ReportItem.report_id == report.id)).all()}
    if set(payload.item_ids) != set(items):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "모든 항목의 ID를 정확히 한 번씩 보내야 합니다")
    for pos, iid in enumerate(payload.item_ids, start=1):
        items[iid].position = pos
    report.lock_version += 1
    db.commit()
    return _detail(db, report)


@router.get("/{report_id}/exports", response_model=list[ReportExportOut])
def list_exports(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_access_files(report, user)
    return db.scalars(select(ReportExport).where(ReportExport.report_id == report.id)
                      .order_by(ReportExport.created_at.desc())).all()


@router.post("/{report_id}/exports", response_model=ReportExportOut, status_code=status.HTTP_201_CREATED)
def create_export(report_id: uuid.UUID, payload: ExportRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_access_files(report, user)
    try:
        export = report_service.generate_export(
            db, report, file_format=payload.file_format, user_id=user.id, final=(report.status == "final"),
        )
    except report_service.ExportInProgressError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    log_action(db, actor_user_id=user.id, action="report.export", entity_type="report", entity_id=report.id,
               detail={"format": payload.file_format, "export_id": str(export.id), "status": export.status})
    db.commit()
    return export


@router.get("/{report_id}/exports/{export_id}/download")
def download_export(report_id: uuid.UUID, export_id: uuid.UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    report = _get_report(db, report_id)
    _assert_can_access_files(report, user)
    export = db.get(ReportExport, export_id)
    if export is None or export.report_id != report.id or export.status != "success" or not export.file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "다운로드할 수 있는 출력본이 없습니다")
    media = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
             if export.file_format == "docx" else "application/pdf")
    return FileResponse(export.file_path, media_type=media, filename=export.file_name or f"report.{export.file_format}")


@router.post("/{report_id}/finalize", response_model=ReportDetailOut)
def finalize(report_id: uuid.UUID, payload: FinalizeRequest, db: Session = Depends(get_db),
             user: User = Depends(require_roles(*APPROVERS))):
    report = _get_report(db, report_id)
    if report.status == "final":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 출력용 확정된 보고서입니다")
    issues = report_service.run_preflight(report_service.build_snapshot(db, report))
    blocking = report_service.blocking_issues(issues)
    reason = (payload.exception_reason or "").strip()
    if blocking and not reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "필수 점검을 통과하지 못해 확정할 수 없습니다 — 해결하거나 승인권자 예외 사유를 입력하세요",
                    "blocking": blocking},
        )
    report.status = "final"
    report.finalize_exception_reason = reason or None
    report.finalized_by_user_id = user.id
    report.finalized_at = datetime.now(timezone.utc)
    report.lock_version += 1
    log_action(db, actor_user_id=user.id, action="report.finalize", entity_type="report", entity_id=report.id,
               detail={"exception_reason": reason or None, "blocking_codes": [b["code"] for b in blocking]})
    db.commit()
    return _detail(db, report)


@router.post("/{report_id}/reopen", response_model=ReportDetailOut)
def reopen(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_roles(*APPROVERS))):
    report = _get_report(db, report_id)
    if report.status != "final":
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 보고서만 해제할 수 있습니다")
    report.status = "draft"
    report.lock_version += 1
    log_action(db, actor_user_id=user.id, action="report.reopen", entity_type="report", entity_id=report.id)
    db.commit()
    return _detail(db, report)


# ---- 템플릿 ----
@template_router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    report_service.get_active_template(db)
    db.commit()
    return db.scalars(select(ReportTemplate).order_by(ReportTemplate.name, ReportTemplate.version.desc())).all()


@template_router.post("/{template_id}/new-version", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def new_template_version(template_id: uuid.UUID, payload: TemplateConfigPatch, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(UserRole.ADMIN))):
    template = db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "템플릿을 찾을 수 없습니다")
    new = report_service.create_template_version(db, template, payload.config, user.id)
    log_action(db, actor_user_id=user.id, action="report_template.new_version", entity_type="report_template",
               entity_id=new.id, detail={"version": new.version})
    db.commit()
    db.refresh(new)
    return new
