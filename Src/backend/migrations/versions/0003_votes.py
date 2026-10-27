"""T17 answers constrained to a poll's slots and participants."""
from alembic import op
import sqlalchemy as sa

revision = '0003_votes'
down_revision = '0002_poll_structure'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('votes',
        sa.Column('poll_id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('availability', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('slot_id', 'user_id'),
        sa.ForeignKeyConstraint(['poll_id', 'slot_id'], ['slots.poll_id', 'slots.id'], ondelete='RESTRICT', name='fk_votes_poll_slot'),
        sa.ForeignKeyConstraint(['poll_id', 'user_id'], ['participants.poll_id', 'participants.user_id'], ondelete='RESTRICT', name='fk_votes_poll_participant'),
        sa.CheckConstraint("availability IN ('AVAILABLE','MAYBE','UNAVAILABLE')", name='ck_votes_availability'),
        sa.CheckConstraint("typeof(updated_at) = 'integer'", name='ck_votes_updated_at'))
    op.create_index('ix_votes_poll_user', 'votes', ['poll_id', 'user_id'], unique=False)


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
