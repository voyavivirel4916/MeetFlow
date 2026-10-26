"""Frozen initial account/group schema. No business data is seeded."""
from alembic import op
import sqlalchemy as sa

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Integer(), nullable=False),
    sa.CheckConstraint("length(username) BETWEEN 3 AND 32 AND username = lower(trim(username)) AND username NOT GLOB '*[^a-z0-9_]*'", name='ck_users_username'),
    sa.CheckConstraint('id > 0', name='ck_users_id'),
    sa.CheckConstraint('length(email) BETWEEN 1 AND 254 AND email = lower(trim(email))', name='ck_users_email'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('username')
    )
    op.create_table('groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('invite_code', sa.Text(), nullable=False),
    sa.Column('invite_enabled', sa.Boolean(create_constraint=True, name='ck_groups_invite_enabled'), server_default='1', nullable=False),
    sa.Column('created_at', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.Integer(), nullable=False),
    sa.CheckConstraint("length(invite_code) = 12 AND invite_code NOT GLOB '*[^A-Z0-9]*'", name='ck_groups_invite_code'),
    sa.CheckConstraint('id > 0', name='ck_groups_id'),
    sa.CheckConstraint('length(description) <= 10000', name='ck_groups_description'),
    sa.CheckConstraint('length(name) BETWEEN 1 AND 100', name='ck_groups_name'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('invite_code')
    )
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.Integer(), nullable=False),
    sa.Column('revoked_at', sa.Integer(), nullable=True),
    sa.CheckConstraint("length(token_hash) = 64 AND token_hash NOT GLOB '*[^0-9a-f]*'", name='ck_sessions_hash'),
    sa.CheckConstraint('expires_at > created_at', name='ck_sessions_expiry'),
    sa.CheckConstraint('id > 0', name='ck_sessions_id'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_sessions_expires_at', 'sessions', ['expires_at'], unique=False)
    op.create_table('group_members',
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('joined_at', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('group_id', 'user_id')
    )
    op.create_index('ix_group_members_user_id', 'group_members', ['user_id'], unique=False)

def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead.")
