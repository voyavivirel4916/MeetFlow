"""Frozen T14 poll, participant and slot schema; preserves account/group data."""
from alembic import op
import sqlalchemy as sa

revision = '0002_poll_structure'
down_revision = '0001_core'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('polls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column('location', sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column('response_deadline', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.CheckConstraint('id > 0', name='ck_polls_id'),
        sa.CheckConstraint('length(title) BETWEEN 1 AND 100', name='ck_polls_title'),
        sa.CheckConstraint('length(description) <= 10000', name='ck_polls_description'),
        sa.CheckConstraint('length(location) <= 200', name='ck_polls_location'),
        sa.CheckConstraint("status IN ('DRAFT','OPEN','CLOSED','CONFIRMED','CANCELLED')", name='ck_polls_status'),
        sa.CheckConstraint("typeof(response_deadline) = 'integer' AND typeof(created_at) = 'integer' AND typeof(updated_at) = 'integer'", name='ck_polls_times'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id', 'group_id', name='uq_polls_id_group'))
    op.create_index('ix_polls_group_status', 'polls', ['group_id', 'status'], unique=False)
    op.create_table('participants',
        sa.Column('poll_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('importance', sa.Text(), nullable=False),
        sa.Column('submitted_at', sa.Integer(), nullable=True),
        sa.CheckConstraint("importance IN ('REQUIRED','NORMAL')", name='ck_participants_importance'),
        sa.CheckConstraint("submitted_at IS NULL OR typeof(submitted_at) = 'integer'", name='ck_participants_submitted_at'),
        sa.ForeignKeyConstraint(['poll_id', 'group_id'], ['polls.id', 'polls.group_id'], ondelete='RESTRICT', name='fk_participants_poll_group'),
        sa.ForeignKeyConstraint(['group_id', 'user_id'], ['group_members.group_id', 'group_members.user_id'], ondelete='RESTRICT', name='fk_participants_group_member'),
        sa.PrimaryKeyConstraint('poll_id', 'user_id'))
    op.create_table('slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('poll_id', sa.Integer(), nullable=False),
        sa.Column('start_at', sa.Integer(), nullable=False),
        sa.Column('end_at', sa.Integer(), nullable=False),
        sa.CheckConstraint('id > 0', name='ck_slots_id'),
        sa.CheckConstraint('start_at < end_at', name='ck_slots_order'),
        sa.CheckConstraint("typeof(start_at) = 'integer' AND typeof(end_at) = 'integer'", name='ck_slots_times'),
        sa.ForeignKeyConstraint(['poll_id'], ['polls.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('poll_id', 'start_at', 'end_at', name='uq_slots_poll_time'),
        sa.UniqueConstraint('poll_id', 'id', name='uq_slots_poll_id'))


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
