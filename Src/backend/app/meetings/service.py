import sqlite3

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from app.common import clock
from app.common.responses import ApiError
from app.common.times import format_ms
from app.db.connection import write_transaction
from app.db.models import meetings, polls, slots
from app.meetings.models import MeetingOut
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
