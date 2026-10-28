"""One-use password reset digests; existing data is untouched."""
from alembic import op
import sqlalchemy as sa

revision = '0008_password_resets'
down_revision = '0007_task_updates'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('password_resets',
        sa.Column('token_hash', sa.Text(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.Integer()),
        sa.CheckConstraint('length(token_hash) = 64', name='ck_reset_hash'),
        sa.CheckConstraint('expires_at > created_at', name='ck_reset_expiry'))
    op.create_index('ix_password_resets_user_created', 'password_resets', ['user_id', 'created_at'])


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup.')
