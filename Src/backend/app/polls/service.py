from sqlalchemy import func, insert, select, update

from app.common import clock
from app.common.responses import ApiError
from app.common.times import format_ms, to_ms
from app.db.connection import write_transaction
from app.db.models import group_members, meetings, participants, polls, slots, users
from app.groups.service import require_member, require_owner
from app.polls.models import DraftIn, ParticipantOut, PollOut, PollPage, SlotOut


def effective_status(row, now):
    return 'CLOSED' if row['status'] == 'OPEN' and row['response_deadline'] <= now else row['status']


def materialize_expiry(connection, row, now):
    if row['status'] == 'OPEN' and effective_status(row, now) == 'CLOSED':
        return _set_status(connection, row, 'CLOSED', now)
    return row


def _set_status(connection, row, status, now):
    connection.execute(update(polls).where(polls.c.id == row['id']).values(status=status, updated_at=now))
    return dict(row, status=status, updated_at=now)


def _not_found():
    return ApiError(404, 'NOT_FOUND', '未找到可访问的排期。')


def _require_poll(connection, user_id, poll_id, *, owner=False, include_deleted=False):
    row = connection.execute(select(polls).where(polls.c.id == poll_id)).mappings().first()
    if row is None or (row['deleted_at'] is not None and not include_deleted):
        raise _not_found()
    try:
        (require_owner if owner else require_member)(connection, user_id, row['group_id'])
    except ApiError as error:
        if error.status == 404:
            raise _not_found() from None
        raise
    return row


def _invalid(field, message):
    return ApiError(422, 'VALIDATION_ERROR', message, {'fields': [{'location': ['body', field], 'type': 'value_error'}]})


def _check_participants(connection, group_id, data):
    identifiers = {item.user_id for item in data.participants}
    if not identifiers:
        return
    members = set(connection.execute(select(group_members.c.user_id)
        .where(group_members.c.group_id == group_id, group_members.c.user_id.in_(identifiers))).scalars())
    if identifiers != members:
        raise _invalid('participants', '参与者必须是当前小组的成员。')


def _children(connection, poll_id, group_id, data):
    if data.participants:
        connection.execute(insert(participants), [dict(poll_id=poll_id, group_id=group_id,
            user_id=item.user_id, importance=item.importance) for item in data.participants])
    if data.slots:
        connection.execute(insert(slots), [dict(poll_id=poll_id, start_at=to_ms(item.start_at), end_at=to_ms(item.end_at)) for item in data.slots])


def _outputs(connection, rows):
    if not rows:
        return []
    identifiers = [row['id'] for row in rows]
    rosters, candidates = {key: [] for key in identifiers}, {key: [] for key in identifiers}
    for item in connection.execute(select(participants, users.c.username).join(users, participants.c.user_id == users.c.id)
            .where(participants.c.poll_id.in_(identifiers)).order_by(participants.c.poll_id, participants.c.user_id)).mappings():
        rosters[item['poll_id']].append(ParticipantOut(user_id=item['user_id'], username=item['username'],
            importance=item['importance'], submitted_at=None if item['submitted_at'] is None else format_ms(item['submitted_at'])))
    for item in connection.execute(select(slots).where(slots.c.poll_id.in_(identifiers))
            .order_by(slots.c.poll_id, slots.c.start_at, slots.c.end_at, slots.c.id)).mappings():
        candidates[item['poll_id']].append(SlotOut(id=item['id'], start_at=format_ms(item['start_at']), end_at=format_ms(item['end_at'])))
    now = clock.now_ms()  # Sample after any blocked read, once for the whole response.
    return [PollOut(**{key: row[key] for key in ['id', 'group_id', 'title', 'description', 'location', 'status']},
        response_deadline=format_ms(row['response_deadline']), effective_status=effective_status(row, now),
        participants=rosters[row['id']], slots=candidates[row['id']], updated_at=format_ms(row['updated_at']),
        deleted_at=None if row['deleted_at'] is None else format_ms(row['deleted_at']),
        archived_at=None if row['archived_at'] is None else format_ms(row['archived_at'])) for row in rows]


def create_draft(engine, user_id, group_id, data: DraftIn):
    with write_transaction(engine) as connection:
        require_owner(connection, user_id, group_id)
        _check_participants(connection, group_id, data)
        now = clock.now_ms()
        identifier = connection.execute(insert(polls).values(group_id=group_id, title=data.title, description=data.description,
            location=data.location, response_deadline=to_ms(data.response_deadline), status='DRAFT', created_at=now, updated_at=now)).inserted_primary_key[0]
        _children(connection, identifier, group_id, data)
        row = connection.execute(select(polls).where(polls.c.id == identifier)).mappings().one()
        result = _outputs(connection, [row])[0]
    return result


def get_poll(engine, user_id, poll_id):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        return _outputs(connection, [_require_poll(connection, user_id, poll_id)])[0]


def list_polls(engine, user_id, group_id, page, page_size, view='current'):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        (require_owner if view == 'trash' else require_member)(connection, user_id, group_id)
        condition = polls.c.group_id == group_id
        if view == 'trash':
            condition = condition & polls.c.deleted_at.is_not(None)
        else:
            condition = condition & polls.c.deleted_at.is_(None)
            condition = condition & (polls.c.archived_at.is_not(None) if view == 'history' else polls.c.archived_at.is_(None))
        total = connection.execute(select(func.count()).select_from(polls).where(condition)).scalar_one()
        offset = (page - 1) * page_size
        rows = [] if offset >= total else connection.execute(select(polls).where(condition)
            .order_by(polls.c.created_at.desc(), polls.c.id.desc()).limit(page_size).offset(offset)).mappings().all()
        return PollPage(items=_outputs(connection, rows), page=page, page_size=page_size, total=total)


def replace_draft(engine, user_id, poll_id, data: DraftIn):
    conflict = None
    with write_transaction(engine) as connection:
        row = _require_poll(connection, user_id, poll_id, owner=True)
        now = clock.now_ms()
        row = materialize_expiry(connection, row, now)
        if row['status'] != 'DRAFT':
            conflict = ApiError(409, 'STATE_CONFLICT', '排期已发布或结束，不能修改草稿结构。')
        else:
            _check_participants(connection, row['group_id'], data)
            connection.execute(update(polls).where(polls.c.id == poll_id).values(title=data.title, description=data.description,
                location=data.location, response_deadline=to_ms(data.response_deadline), updated_at=now))
            connection.execute(slots.delete().where(slots.c.poll_id == poll_id))
            connection.execute(participants.delete().where(participants.c.poll_id == poll_id))
            _children(connection, poll_id, row['group_id'], data)
            result = _outputs(connection, [connection.execute(select(polls).where(polls.c.id == poll_id)).mappings().one()])[0]
    # Keep an authorized expiry transition even when the requested edit is refused.
    if conflict:
        raise conflict
    return result


def organize_poll(engine, user_id, poll_id, action):
    """Serialize visibility changes with confirmation and every existing poll write."""
    with write_transaction(engine) as connection:
        row = _require_poll(connection, user_id, poll_id, owner=True,
                            include_deleted=action in {'delete', 'restore'})
        now = clock.now_ms()
        row = materialize_expiry(connection, row, now)
        changes = {}
        if action == 'delete':
            linked = connection.execute(select(meetings.c.id).where(meetings.c.poll_id == poll_id)).first()
            if row['status'] not in {'DRAFT', 'CLOSED', 'CANCELLED'} or linked:
                raise ApiError(409, 'STATE_CONFLICT', '收集中请先取消；已有会议的排期请归档。')
            if row['deleted_at'] is None:
                changes['deleted_at'] = now
        elif action == 'restore':
            if row['deleted_at'] is not None:
                changes['deleted_at'] = None
        elif action in {'archive', 'unarchive'}:
            if row['status'] != 'CONFIRMED':
                raise ApiError(409, 'STATE_CONFLICT', '只有已确认会议的排期可以归档或取消归档。')
            if action == 'archive' and row['archived_at'] is None:
                changes['archived_at'] = now
            elif action == 'unarchive' and row['archived_at'] is not None:
                changes['archived_at'] = None
        else:
            raise ValueError('Unknown organization action')
        if changes:
            changes['updated_at'] = max(now, row['updated_at'])
            connection.execute(update(polls).where(polls.c.id == poll_id).values(**changes))
            row = dict(row, **changes)
        return _outputs(connection, [row])[0]


def _check_publish(connection, row, now):
    roster = connection.execute(select(participants.c.user_id).where(participants.c.poll_id == row['id'])).scalars().all()
    candidates = connection.execute(select(slots.c.start_at).where(slots.c.poll_id == row['id'])).scalars().all()
    if not roster:
        raise _invalid('participants', '发布前请至少选择一位组内参与者。')
    members = set(connection.execute(select(group_members.c.user_id).where(group_members.c.group_id == row['group_id'])).scalars())
    if not set(roster) <= members:
        raise _invalid('participants', '参与者必须是当前小组的成员。')
    if not 1 <= len(candidates) <= 15:
        raise _invalid('slots', '发布前请设置1～15个候选时段。')
    if row['response_deadline'] <= now or any(start <= row['response_deadline'] for start in candidates):
        raise _invalid('response_deadline', '填写截止须在未来，且早于每个候选开始时间。')


def transition_poll(engine, user_id, poll_id, action):
    conflict = None
    with write_transaction(engine) as connection:
        row = _require_poll(connection, user_id, poll_id, owner=True)
        now = clock.now_ms()
        row = materialize_expiry(connection, row, now)
        status = row['status']
        if action == 'open' and status == 'DRAFT':
            _check_publish(connection, row, now)
            row = _set_status(connection, row, 'OPEN', now)
        elif action == 'close' and status in {'OPEN', 'CLOSED'}:
            if status == 'OPEN':
                row = _set_status(connection, row, 'CLOSED', now)
        elif action == 'cancel' and status in {'DRAFT', 'OPEN', 'CLOSED', 'CANCELLED'}:
            if status != 'CANCELLED':
                row = _set_status(connection, row, 'CANCELLED', now)
        else:
            conflict = ApiError(409, 'STATE_CONFLICT', '当前排期状态不允许执行此操作。')
        if not conflict:
            result = _outputs(connection, [row])[0]
    if conflict:
        raise conflict
    return result
