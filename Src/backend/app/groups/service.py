import secrets
import sqlite3
import string

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.common import clock
from app.common.responses import ApiError
from app.db.connection import write_transaction
from app.db.models import group_members, groups, users
from app.groups.models import GroupIn, GroupOut, GroupPage, InviteOut, MemberList, MemberOut

MAX_MEMBERS = 20
INVITE_ATTEMPTS = 3


def generate_invite_code():
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))


def _invite_collision(error):
    return (getattr(error.orig, 'sqlite_errorcode', None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE
            and str(error.orig) == 'UNIQUE constraint failed: groups.invite_code')


def _invite_unavailable():
    return ApiError(503, 'STORAGE_UNAVAILABLE', '暂时无法生成新的邀请码，请稍后核对并重试。')


def _not_found():
    return ApiError(404, 'NOT_FOUND', '未找到可访问的小组。')


def require_member(connection, user_id: int, group_id: int):
    """Reusable group boundary; never reveal a group to a non-member."""
    row = connection.execute(select(groups).join(group_members, groups.c.id == group_members.c.group_id)
        .where(groups.c.id == group_id, group_members.c.user_id == user_id)).mappings().first()
    if row is None:
        raise _not_found()
    return row


def require_owner(connection, user_id: int, group_id: int):
    row = require_member(connection, user_id, group_id)
    if row['owner_id'] != user_id:
        raise ApiError(403, 'FORBIDDEN', '只有小组负责人可以执行此操作。')
    return row


def _count(connection, group_id):
    return connection.execute(select(func.count()).select_from(group_members)
                              .where(group_members.c.group_id == group_id)).scalar_one()


def _out(row, user_id, member_count):
    fields = {key: row[key] for key in ['id', 'name', 'description', 'owner_id']}
    if row['owner_id'] == user_id:
        fields.update(invite_code=row['invite_code'], invite_enabled=row['invite_enabled'])
    return GroupOut(**fields, member_count=member_count)


def create_group(engine, user_id: int, data: GroupIn):
    for _ in range(INVITE_ATTEMPTS):
        try:
            with write_transaction(engine) as connection:
                now = clock.now_ms()
                identifier = connection.execute(insert(groups).values(name=data.name, description=data.description,
                    owner_id=user_id, invite_code=generate_invite_code(), invite_enabled=True,
                    created_at=now, updated_at=now)).inserted_primary_key[0]
                connection.execute(insert(group_members).values(group_id=identifier, user_id=user_id, joined_at=now))
                result = _out(require_member(connection, user_id, identifier), user_id, 1)
            return result
        except IntegrityError as error:
            if not _invite_collision(error):
                raise
    raise _invite_unavailable()


def list_groups(engine, user_id: int, page: int, page_size: int):
    with engine.connect() as connection:
        # A stable snapshot keeps total and this page consistent during concurrent joins.
        connection.exec_driver_sql('BEGIN')
        membership = groups.join(group_members, groups.c.id == group_members.c.group_id)
        condition = group_members.c.user_id == user_id
        total = connection.execute(select(func.count()).select_from(membership).where(condition)).scalar_one()
        offset = (page - 1) * page_size
        items = []
        if offset < total:
            member_count = (select(func.count()).select_from(group_members)
                .where(group_members.c.group_id == groups.c.id).correlate(groups).scalar_subquery())
            rows = connection.execute(select(groups, member_count.label('member_count')).select_from(membership)
                .where(condition).order_by(groups.c.created_at.desc(), groups.c.id.desc())
                .offset(offset).limit(page_size)).mappings()
            items = [_out(row, user_id, row['member_count']) for row in rows]
    return GroupPage(items=items, page=page, page_size=page_size, total=total)


def get_group(engine, user_id: int, group_id: int):
    with engine.connect() as connection:
        row = require_member(connection, user_id, group_id)
        return _out(row, user_id, _count(connection, group_id))


def list_members(engine, user_id: int, group_id: int):
    with engine.connect() as connection:
        group = require_member(connection, user_id, group_id)
        rows = connection.execute(select(users.c.id, users.c.username).join(group_members,
            users.c.id == group_members.c.user_id).where(group_members.c.group_id == group_id)
            .order_by(group_members.c.joined_at, users.c.id)).mappings()
        return MemberList(items=[MemberOut(user_id=row['id'], username=row['username'],
            role='OWNER' if row['id'] == group['owner_id'] else 'MEMBER') for row in rows])


def join_group(engine, user_id: int, invite_code: str):
    with write_transaction(engine) as connection:
        row = connection.execute(select(groups).where(groups.c.invite_code == invite_code)).mappings().first()
        if row is None:
            raise _not_found()
        existing = connection.execute(select(group_members.c.user_id)
            .where(group_members.c.group_id == row['id'], group_members.c.user_id == user_id)).first()
        count = _count(connection, row['id'])
        if existing:
            result = _out(row, user_id, count)
        else:
            if not row['invite_enabled']:
                raise _not_found()
            if count >= MAX_MEMBERS:
                raise ApiError(409, 'STATE_CONFLICT', '小组已满20人，暂时无法加入。')
            connection.execute(insert(group_members).values(group_id=row['id'], user_id=user_id, joined_at=clock.now_ms()))
            result = _out(row, user_id, count + 1)
    return result


def reset_invite(engine, user_id: int, group_id: int):
    for _ in range(INVITE_ATTEMPTS):
        try:
            with write_transaction(engine) as connection:
                row = require_owner(connection, user_id, group_id)
                code = generate_invite_code()
                if code == row['invite_code']:
                    continue
                connection.execute(update(groups).where(groups.c.id == group_id)
                    .values(invite_code=code, invite_enabled=True, updated_at=clock.now_ms()))
            return InviteOut(invite_code=code)
        except IntegrityError as error:
            if not _invite_collision(error):
                raise
    raise _invite_unavailable()
