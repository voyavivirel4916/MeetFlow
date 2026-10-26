from sqlalchemy import (Boolean, CheckConstraint, Column, ForeignKey, Index,
                        Integer, MetaData, Table, Text, text)

# Core tables only. Poll/meeting/task schemas arrive with their implementation tasks.
metadata = MetaData()
users = Table('users', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', Text, nullable=False, unique=True),
    Column('email', Text, nullable=False, unique=True),
    Column('password_hash', Text, nullable=False),
    Column('created_at', Integer, nullable=False),
    CheckConstraint('id > 0', name='ck_users_id'),
    CheckConstraint("length(username) BETWEEN 3 AND 32 AND username = lower(trim(username)) AND username NOT GLOB '*[^a-z0-9_]*'", name='ck_users_username'),
    CheckConstraint('length(email) BETWEEN 1 AND 254 AND email = lower(trim(email))', name='ck_users_email'))
sessions = Table('sessions', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
    Column('token_hash', Text, nullable=False, unique=True),
    Column('created_at', Integer, nullable=False),
    Column('expires_at', Integer, nullable=False),
    Column('revoked_at', Integer),
    CheckConstraint('id > 0', name='ck_sessions_id'),
    CheckConstraint("length(token_hash) = 64 AND token_hash NOT GLOB '*[^0-9a-f]*'", name='ck_sessions_hash'),
    CheckConstraint('expires_at > created_at', name='ck_sessions_expiry'))
Index('ix_sessions_expires_at', sessions.c.expires_at)
groups = Table('groups', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False),
    Column('description', Text, nullable=False, server_default=text("''")),
    Column('owner_id', Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
    Column('invite_code', Text, nullable=False, unique=True),
    Column('invite_enabled', Boolean(create_constraint=True, name='ck_groups_invite_enabled'), nullable=False, server_default='1'),
    Column('created_at', Integer, nullable=False),
    Column('updated_at', Integer, nullable=False),
    CheckConstraint('id > 0', name='ck_groups_id'),
    CheckConstraint('length(name) BETWEEN 1 AND 100', name='ck_groups_name'),
    CheckConstraint('length(description) <= 10000', name='ck_groups_description'),
    CheckConstraint("length(invite_code) = 12 AND invite_code NOT GLOB '*[^A-Z0-9]*'", name='ck_groups_invite_code'))
group_members = Table('group_members', metadata,
    Column('group_id', Integer, ForeignKey('groups.id', ondelete='RESTRICT'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='RESTRICT'), primary_key=True),
    Column('joined_at', Integer, nullable=False))
Index('ix_group_members_user_id', group_members.c.user_id)
