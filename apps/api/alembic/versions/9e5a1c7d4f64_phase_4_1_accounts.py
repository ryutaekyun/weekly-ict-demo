"""phase 4.1 accounts: approval status, invites

Revision ID: 9e5a1c7d4f64
Revises: 8d4f0b6c3e53
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "9e5a1c7d4f64"
down_revision = "8d4f0b6c3e53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("approval_status", sa.String(20), nullable=False, server_default="approved"))
        b.add_column(sa.Column("favorite_fields_json", sa.Text(), nullable=True))
        b.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("registered_via", sa.String(20), nullable=False, server_default="seed"))
    op.create_table(
        "user_invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_user_invites_email", "user_invites", ["email"])


def downgrade() -> None:
    op.drop_index("ix_user_invites_email", table_name="user_invites")
    op.drop_table("user_invites")
    with op.batch_alter_table("users") as b:
        for c in ("registered_via", "approved_at", "last_login_at", "favorite_fields_json", "approval_status"):
            b.drop_column(c)
