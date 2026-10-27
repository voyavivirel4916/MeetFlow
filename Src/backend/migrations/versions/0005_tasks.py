"""T28 tasks, group boundaries and creation request deduplication."""
from alembic import op
import sqlalchemy as sa

revision = '0005_tasks'
down_revision = '0004_meetings'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('uq_meetings_id_group', 'meetings', ['id', 'group_id'], unique=True)
    op.create_table('tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('creator_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('assignee_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('due_at', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'TODO'")),
        sa.Column('completed_at', sa.Integer()),
        sa.Column('client_request_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.UniqueConstraint('creator_id', 'client_request_id', name='uq_tasks_creator_request'),
        sa.ForeignKeyConstraint(['meeting_id', 'group_id'], ['meetings.id', 'meetings.group_id'], ondelete='RESTRICT', name='fk_tasks_meeting_group'),
        sa.ForeignKeyConstraint(['group_id', 'assignee_id'], ['group_members.group_id', 'group_members.user_id'], ondelete='RESTRICT', name='fk_tasks_assignee_member'),
        sa.CheckConstraint('id > 0', name='ck_tasks_id'),
        sa.CheckConstraint('length(title) BETWEEN 1 AND 100', name='ck_tasks_title'),
        sa.CheckConstraint('length(description) <= 10000', name='ck_tasks_description'),
        sa.CheckConstraint("status IN ('TODO','IN_PROGRESS','DONE')", name='ck_tasks_status'),
        sa.CheckConstraint("(status = 'DONE' AND completed_at IS NOT NULL) OR (status != 'DONE' AND completed_at IS NULL)", name='ck_tasks_completion'),
        sa.CheckConstraint('due_at > created_at', name='ck_tasks_deadline'),
        sa.CheckConstraint("typeof(due_at) = 'integer' AND typeof(created_at) = 'integer' AND typeof(updated_at) = 'integer' AND (completed_at IS NULL OR typeof(completed_at) = 'integer')", name='ck_tasks_times'),
        sa.CheckConstraint("length(client_request_id) = 36 AND substr(client_request_id,9,1) = '-' AND substr(client_request_id,14,1) = '-' AND substr(client_request_id,19,1) = '-' AND substr(client_request_id,24,1) = '-' AND length(replace(client_request_id,'-','')) = 32 AND replace(client_request_id,'-','') NOT GLOB '*[^0-9a-f]*'", name='ck_tasks_request_id'))
    op.create_index('ix_tasks_assignee_status_due', 'tasks', ['assignee_id', 'status', 'due_at'])
    op.create_index('ix_tasks_group_created', 'tasks', ['group_id', 'created_at'])


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
