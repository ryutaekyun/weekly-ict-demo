"""phase 3_5 demo integration

후보주제 담당자, 요약 항목 핵심 사실 재검토 기록, 주간기술동향지 심의 예외 사유.

Revision ID: 4b6d6e61287c
Revises: e0863abd4939
Create Date: 2026-10-26 20:22:31.448830

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b6d6e61287c'
down_revision = 'e0863abd4939'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite는 ALTER로 외래키를 추가할 수 없으므로 batch로 처리한다(PostgreSQL에서도 동일하게 동작)
    with op.batch_alter_table('candidates') as batch:
        batch.add_column(sa.Column('assignee_user_id', sa.Uuid(), nullable=True))
        batch.create_foreign_key('fk_candidates_assignee_user', 'users', ['assignee_user_id'], ['id'])
    with op.batch_alter_table('report_items') as batch:
        batch.add_column(sa.Column('fact_review_status', sa.String(length=12), nullable=True))
        batch.add_column(sa.Column('fact_review_note', sa.Text(), nullable=True))
        batch.add_column(sa.Column('fact_reviewed_by_user_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('fact_reviewed_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('fact_reviewed_lock_version', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_report_items_fact_reviewer', 'users', ['fact_reviewed_by_user_id'], ['id'])
    with op.batch_alter_table('tj_decisions') as batch:
        batch.add_column(sa.Column('exception_reason', sa.Text(), nullable=True))
        batch.add_column(sa.Column('unresolved_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('tj_decisions') as batch:
        batch.drop_column('unresolved_count')
        batch.drop_column('exception_reason')
    with op.batch_alter_table('report_items') as batch:
        batch.drop_constraint('fk_report_items_fact_reviewer', type_='foreignkey')
        batch.drop_column('fact_reviewed_lock_version')
        batch.drop_column('fact_reviewed_at')
        batch.drop_column('fact_reviewed_by_user_id')
        batch.drop_column('fact_review_note')
        batch.drop_column('fact_review_status')
    with op.batch_alter_table('candidates') as batch:
        batch.drop_constraint('fk_candidates_assignee_user', type_='foreignkey')
        batch.drop_column('assignee_user_id')
