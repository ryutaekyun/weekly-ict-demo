"""phase 4.2 collection jobs, source operation settings, document versions

Revision ID: af6b2d8e5a75
Revises: 9e5a1c7d4f64
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "af6b2d8e5a75"
down_revision = "9e5a1c7d4f64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as b:
        b.alter_column("source_type", existing_type=sa.String(4), type_=sa.String(20), existing_nullable=False)
        b.add_column(sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="1440"))
        b.add_column(sa.Column("min_request_interval_seconds", sa.Float(), nullable=False, server_default="3.0"))
        b.add_column(sa.Column("respect_robots", sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("access_status", sa.String(20), nullable=False, server_default="unverified"))
        b.add_column(sa.Column("access_note", sa.Text(), nullable=True))
        b.add_column(sa.Column("last_new_count", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("config_json", sa.Text(), nullable=True))
        b.add_column(sa.Column("description", sa.Text(), nullable=True))
    with op.batch_alter_table("source_documents") as b:
        b.alter_column("collection_method", existing_type=sa.String(4), type_=sa.String(20), existing_nullable=False)
        b.add_column(sa.Column("external_id", sa.String(255), nullable=True))
        b.add_column(sa.Column("normalized_url", sa.String(1000), nullable=True))
        b.add_column(sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"))
        b.create_index("ix_source_documents_external_id", ["external_id"])
        b.create_index("ix_source_documents_normalized_url", ["normalized_url"])
    op.create_table(
        "collection_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("requested_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("active_key", sa.String(40), nullable=True, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage", sa.String(60), nullable=True),
        sa.Column("items_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_classified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_type", sa.String(40), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("collection_runs.id"), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_collection_jobs_source_id", "collection_jobs", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_jobs_source_id", table_name="collection_jobs")
    op.drop_table("collection_jobs")
    with op.batch_alter_table("source_documents") as b:
        b.drop_index("ix_source_documents_normalized_url")
        b.drop_index("ix_source_documents_external_id")
        for c in ("version_no", "is_latest", "normalized_url", "external_id"):
            b.drop_column(c)
    with op.batch_alter_table("sources") as b:
        for c in ("description", "config_json", "last_new_count", "access_note", "access_status", "respect_robots", "min_request_interval_seconds", "interval_minutes"):
            b.drop_column(c)
