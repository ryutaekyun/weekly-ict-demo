"""phase 3.6.2a first real call safeguards: approvals, evaluations, raw response

Revision ID: 7c3e9a5b2d42
Revises: 6b2d8e4f1a31
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "7c3e9a5b2d42"
down_revision = "6b2d8e4f1a31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_analyses") as b:
        b.add_column(sa.Column("raw_response_text", sa.Text(), nullable=True))
    op.create_table(
        "ai_call_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("max_cost_usd", sa.Float(), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ai_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_user_id", sa.Uuid(), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("scores_json", sa.Text(), nullable=False),
        sa.Column("semantic_mismatch_cases", sa.Integer(), nullable=False),
        sa.Column("insufficient_evidence_cases", sa.Integer(), nullable=False),
        sa.Column("wrong_source_cases", sa.Integer(), nullable=False),
        sa.Column("auto_stats_json", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["ai_analyses.id"]),
        sa.ForeignKeyConstraint(["evaluator_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_evaluations_analysis_id", "ai_evaluations", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_evaluations_analysis_id", table_name="ai_evaluations")
    op.drop_table("ai_evaluations")
    op.drop_table("ai_call_approvals")
    with op.batch_alter_table("ai_analyses") as b:
        b.drop_column("raw_response_text")
