import sqlite3

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.common import clock
from app.common.responses import ApiError
from app.common.times import format_ms
from app.db.connection import write_transaction
from app.db.models import meetings, polls, slots
from app.meetings.models import MeetingOut, MeetingPage
from app.groups.service import require_member, require_owner
from app.polls.service import _invalid, _require_poll, materialize_expiry
from app.recommendations.service import rank_matrix
from app.votes.service import matrix_for_poll


def _find(connection, poll_id):
    return connection.execute(select(meetings).where(meetings.c.poll_id == poll_id)).mappings().first()


def _out(row):
    return MeetingOut(**{key: row[key] for key in ['id', 'poll_id', 'group_id', 'selected_slot_id', 'title', 'location', 'selection_reason', 'agenda', 'minutes']},
        start_at=format_ms(row['start_at']), end_at=format_ms(row['end_at']), updated_at=format_ms(row['updated_at']))


def _repeat(row, slot_id):
    if row['selected_slot_id'] != slot_id:
        raise ApiError(409, 'STATE_CONFLICT', '该排期已确认其他时段，不能覆盖原会议。')
    return _out(row), False


def get_for_poll(engine, user_id, poll_id):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        _require_poll(connection, user_id, poll_id)
        row = _find(connection, poll_id)
        return None if row is None else _out(row)


def _require_meeting(connection, user_id, meeting_id, *, owner=False):
    row = connection.execute(select(meetings).where(meetings.c.id == meeting_id)).mappings().first()
    not_found = ApiError(404, 'NOT_FOUND', '未找到可访问的会议。')
    if row is None:
        raise not_found
    try:
        (require_owner if owner else require_member)(connection, user_id, row['group_id'])
    except ApiError as error:
        if error.status == 404:
            raise not_found from None
        raise
    return row


def get_meeting(engine, user_id, meeting_id):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        return _out(_require_meeting(connection, user_id, meeting_id))


def list_meetings(engine, user_id, group_id, page, page_size):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        require_member(connection, user_id, group_id)
        condition = meetings.c.group_id == group_id
        total = connection.execute(select(func.count()).select_from(meetings).where(condition)).scalar_one()
        offset = (page - 1) * page_size
        rows = [] if offset >= total else connection.execute(select(meetings).where(condition)
            .order_by(meetings.c.start_at.desc(), meetings.c.id.desc()).offset(offset).limit(page_size)).mappings().all()
        return MeetingPage(items=[_out(row) for row in rows], page=page, page_size=page_size, total=total)


def update_meeting(engine, user_id, meeting_id, data):
    with write_transaction(engine) as connection:
        row = _require_meeting(connection, user_id, meeting_id, owner=True)
        fields = data.model_dump(exclude_unset=True)
        # Same content retries preserve the previous saved result and timestamp.
        if any(row[key] != value for key, value in fields.items()):
            connection.execute(update(meetings).where(meetings.c.id == meeting_id)
                .values(**fields, updated_at=max(clock.now_ms(), row['updated_at'])))
        return _out(_require_meeting(connection, user_id, meeting_id))


def confirm(engine, user_id, poll_id, data):
    try:
        with write_transaction(engine) as connection:
            poll = _require_poll(connection, user_id, poll_id, owner=True)
            existing = _find(connection, poll_id)
            if existing is not None:
                return _repeat(existing, data.slot_id)
            now = clock.now_ms()
            poll = materialize_expiry(connection, poll, now)
            if poll['status'] != 'CLOSED':
                raise ApiError(409, 'STATE_CONFLICT', '请先结束收集，关闭后的排期才能确认会议。')
            slot = connection.execute(select(slots).where(slots.c.poll_id == poll_id, slots.c.id == data.slot_id)).mappings().first()
            if slot is None:
                raise _invalid('slot_id', '请选择本次排期的有效候选时间。')
            ranking = rank_matrix(matrix_for_poll(connection, poll))
            selected = next(item for item in ranking if item.slot_id == data.slot_id)
            risk = selected.rank != 1 or selected.required_unavailable_count > 0 or selected.required_unsubmitted_count > 0
            if risk and (not data.acknowledged or not data.selection_reason):
                raise ApiError(400, 'ACK_REQUIRED', '有必到冲突、必到未填或选择非首位时，请确认风险并填写1～500字理由。')
            identifier = connection.execute(insert(meetings).values(poll_id=poll_id, group_id=poll['group_id'], selected_slot_id=slot['id'],
                title=poll['title'], location=poll['location'], start_at=slot['start_at'], end_at=slot['end_at'],
                selection_reason=data.selection_reason, agenda='', minutes='', created_at=now, updated_at=now)).inserted_primary_key[0]
            connection.execute(update(polls).where(polls.c.id == poll_id).values(status='CONFIRMED', updated_at=now))
            result = _out(connection.execute(select(meetings).where(meetings.c.id == identifier)).mappings().one())
        return result, True
    except IntegrityError as error:
        # Only the intended one-meeting-per-poll constraint is idempotent.
        if getattr(error.orig, 'sqlite_errorcode', None) != sqlite3.SQLITE_CONSTRAINT_UNIQUE or str(error.orig) != 'UNIQUE constraint failed: meetings.poll_id':
            raise
        with engine.connect() as connection:
            connection.exec_driver_sql('BEGIN')
            _require_poll(connection, user_id, poll_id, owner=True)
            existing = _find(connection, poll_id)
            if existing is None:
                raise
            return _repeat(existing, data.slot_id)
