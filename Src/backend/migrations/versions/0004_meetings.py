"""T24 unique meeting snapshots, linked to their poll, group and frozen candidate."""
from alembic import op
import sqlalchemy as sa

revision = '0004_meetings'
down_revision = '0003_votes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('meetings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('poll_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('selected_slot_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('start_at', sa.Integer(), nullable=False),
        sa.Column('end_at', sa.Integer(), nullable=False),
        sa.Column('selection_reason', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('agenda', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('minutes', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.UniqueConstraint('poll_id'),
        sa.ForeignKeyConstraint(['poll_id', 'group_id'], ['polls.id', 'polls.group_id'], ondelete='RESTRICT', name='fk_meetings_poll_group'),
        sa.ForeignKeyConstraint(['poll_id', 'selected_slot_id'], ['slots.poll_id', 'slots.id'], ondelete='RESTRICT', name='fk_meetings_poll_slot'),
        sa.CheckConstraint('id > 0', name='ck_meetings_id'),
        sa.CheckConstraint('length(title) BETWEEN 1 AND 100', name='ck_meetings_title'),
        sa.CheckConstraint('length(location) <= 200', name='ck_meetings_location'),
        sa.CheckConstraint('start_at < end_at', name='ck_meetings_order'),
        sa.CheckConstraint('length(selection_reason) <= 500', name='ck_meetings_selection_reason'),
        sa.CheckConstraint('length(agenda) <= 10000 AND length(minutes) <= 10000', name='ck_meetings_notes'),
        sa.CheckConstraint("typeof(start_at) = 'integer' AND typeof(end_at) = 'integer' AND typeof(created_at) = 'integer' AND typeof(updated_at) = 'integer'", name='ck_meetings_times'))
    op.create_index('ix_meetings_group_id', 'meetings', ['group_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
