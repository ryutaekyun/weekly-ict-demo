"""phase 3.6.1 ai hardening: error codes, price settings, insertions

Revision ID: 6b2d8e4f1a31
Revises: 5a1c7d3e9b20
Create Date: 2026-10-27
"""
import uuid
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "6b2d8e4f1a31"
down_revision = "5a1c7d3e9b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_analyses") as b:
        b.add_column(sa.Column("error_code", sa.String(30), nullable=True))
        b.add_column(sa.Column("provider_request_sent", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("pricing_version", sa.String(60), nullable=True))
        b.add_column(sa.Column("cancel_note", sa.Text(), nullable=True))
        b.add_column(sa.Column("source_changed_during_run", sa.Boolean(), nullable=False, server_default=sa.false()))
    price = op.create_table(
        "ai_price_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("input_per_mtok", sa.Float(), nullable=False),
        sa.Column("output_per_mtok", sa.Float(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source_note", sa.String(300), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    note = "공식 가격표(platform.claude.com/docs/en/about-claude/pricing·models/overview) 2026-10-27 확인 — 관리자가 갱신하세요"
    rows = [("claude-fable-5-1", 10.0, 50.0), ("claude-opus-5-5", 4.0, 20.0), ("claude-sonnet-5-5", 2.0, 10.0), ("claude-haiku-5-5", 0.10, 0.50)]
    op.bulk_insert(price, [
        {"id": uuid.uuid4(), "provider": "anthropic", "model": m, "input_per_mtok": i, "output_per_mtok": o, "effective_date": date(2026, 10, 27),
         "source_note": note + ("(Haiku는 'From' 가격)" if "haiku" in m else ""), "version": 1, "is_active": True} for m, i, o in rows
    ])
    op.create_table(
        "ai_insertions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("manuscript_id", sa.Uuid(), nullable=False),
        sa.Column("footnote_mark_id", sa.String(64), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("inserted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("ai_text", sa.Text(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("edited_by_researcher", sa.Boolean(), nullable=False),
        sa.Column("quote_at_insert", sa.Text(), nullable=True),
        sa.Column("source_hash_at_insert", sa.String(64), nullable=True),
        sa.Column("baseline_hash", sa.String(64), nullable=True),
        sa.Column("position_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("last_review_resolution", sa.String(16), nullable=True),
        sa.Column("last_review_note", sa.Text(), nullable=True),
        sa.Column("last_reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_review_hash", sa.String(64), nullable=True),
        sa.Column("review_history_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["ai_analyses.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["ai_claims.id"]),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["inserted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["last_reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_insertions_manuscript_id", "ai_insertions", ["manuscript_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_insertions_manuscript_id", table_name="ai_insertions")
    op.drop_table("ai_insertions")
    op.drop_table("ai_price_settings")
    with op.batch_alter_table("ai_analyses") as b:
        for c in ("source_changed_during_run", "cancel_note", "pricing_version", "provider_request_sent", "error_code"):
            b.drop_column(c)
