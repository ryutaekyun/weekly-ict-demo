"""phase 3.6 ai analysis

Revision ID: 5a1c7d3e9b20
Revises: 4b6d6e61287c
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "5a1c7d3e9b20"
down_revision = "4b6d6e61287c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("verification_status", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_documents_json", sa.Text(), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False),
        sa.Column("est_input_tokens", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("est_cost_usd", sa.Float(), nullable=False),
        sa.Column("actual_cost_usd", sa.Float(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("notes_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.Column("reused_from_id", sa.Uuid(), nullable=True),
        sa.Column("linked_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("public_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("public_approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["linked_candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["public_approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_analyses_request_key", "ai_analyses", ["request_key"])
    op.create_table(
        "ai_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.String(40), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(16), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("evidence_status", sa.String(16), nullable=False),
        sa.Column("check_note", sa.Text(), nullable=True),
        sa.Column("researcher_status", sa.String(12), nullable=False),
        sa.Column("researcher_note", sa.Text(), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inserted_manuscript_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["ai_analyses.id"]),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["inserted_manuscript_id"], ["manuscripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_claims_analysis_id", "ai_claims", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_claims_analysis_id", table_name="ai_claims")
    op.drop_table("ai_claims")
    op.drop_index("ix_ai_analyses_request_key", table_name="ai_analyses")
    op.drop_table("ai_analyses")
