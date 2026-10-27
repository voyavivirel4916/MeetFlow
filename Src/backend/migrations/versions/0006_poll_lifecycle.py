"""Reversible visibility markers; preserve referenced poll rows and answers."""
from alembic import op
import sqlalchemy as sa

revision = '0006_poll_lifecycle'
down_revision = '0005_tasks'
branch_labels = None
depends_on = None


def upgrade():
    # Native ADD COLUMN avoids rebuilding a parent table with live foreign keys.
    op.add_column('polls', sa.Column('archived_at', sa.Integer(),
        sa.CheckConstraint("archived_at IS NULL OR (typeof(archived_at) = 'integer' AND status = 'CONFIRMED')", name='ck_polls_archive')))
    op.add_column('polls', sa.Column('deleted_at', sa.Integer(),
        sa.CheckConstraint("deleted_at IS NULL OR (typeof(deleted_at) = 'integer' AND status IN ('DRAFT','CLOSED','CANCELLED') AND archived_at IS NULL)", name='ck_polls_deletion')))
    op.create_index('ix_polls_group_visibility', 'polls', ['group_id', 'deleted_at', 'archived_at'])


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
