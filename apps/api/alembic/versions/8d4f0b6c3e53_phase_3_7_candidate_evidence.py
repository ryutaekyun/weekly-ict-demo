"""phase 3.7 candidate evidence add/exclude

Revision ID: 8d4f0b6c3e53
Revises: 7c3e9a5b2d42
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "8d4f0b6c3e53"
down_revision = "7c3e9a5b2d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        b.add_column(sa.Column("evidence_extra_json", sa.Text(), nullable=True))
        b.add_column(sa.Column("evidence_excluded_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        b.drop_column("evidence_excluded_json")
        b.drop_column("evidence_extra_json")
