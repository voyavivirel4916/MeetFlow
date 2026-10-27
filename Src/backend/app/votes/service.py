from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from app.common import clock
from app.common.responses import ApiError
from app.common.times import format_ms
from app.db.connection import write_transaction
from app.db.models import participants, slots, votes
from app.polls.service import _invalid, _require_poll, materialize_expiry
from app.votes.models import VoteOut, VotesIn, VotesOut


def _participant(connection, user_id, poll_id):
    row = connection.execute(select(participants).where(
        participants.c.poll_id == poll_id, participants.c.user_id == user_id)).mappings().first()
    if row is None:
        raise ApiError(403, 'FORBIDDEN', '只有本次排期的参与者可以查看或填写本人答案。')
    return row


def _output(connection, user_id, poll_id, submitted_at):
    rows = connection.execute(select(votes.c.slot_id, votes.c.availability).where(
        votes.c.poll_id == poll_id, votes.c.user_id == user_id).order_by(votes.c.slot_id)).mappings()
    return VotesOut(poll_id=poll_id, submitted_at=None if submitted_at is None else format_ms(submitted_at),
        votes=[VoteOut(**row) for row in rows])


def get_votes(engine, user_id, poll_id):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        _require_poll(connection, user_id, poll_id)
        person = _participant(connection, user_id, poll_id)
        return _output(connection, user_id, poll_id, person['submitted_at'])


def save_votes(engine, user_id, poll_id, data: VotesIn):
    conflict = None
    try:
        with write_transaction(engine) as connection:
            row = _require_poll(connection, user_id, poll_id)
            _participant(connection, user_id, poll_id)
            now = clock.now_ms()  # Read only after acquiring the shared poll write lock.
            row = materialize_expiry(connection, row, now)
            if row['status'] != 'OPEN':
                conflict = ApiError(409, 'POLL_CLOSED' if row['status'] == 'CLOSED' else 'STATE_CONFLICT',
                    '排期已截止或当前状态不允许填写。')
            else:
                expected = set(connection.execute(select(slots.c.id).where(slots.c.poll_id == poll_id)).scalars())
                if {item.slot_id for item in data.votes} != expected:
                    raise _invalid('votes', '请完整填写本次排期的全部候选时段，不可遗漏或包含其他排期时段。')
                # Replace only this actor's complete answer; rollback restores old rows on any failure.
                connection.execute(votes.delete().where(votes.c.poll_id == poll_id, votes.c.user_id == user_id))
                connection.execute(insert(votes), [dict(poll_id=poll_id, user_id=user_id,
                    slot_id=item.slot_id, availability=item.availability, updated_at=now) for item in data.votes])
                connection.execute(update(participants).where(participants.c.poll_id == poll_id,
                    participants.c.user_id == user_id).values(submitted_at=now))
                result = _output(connection, user_id, poll_id, now)
    except IntegrityError:
        raise ApiError(409, 'STATE_CONFLICT', '答案保存发生冲突，请重新读取排期后再试。') from None
    if conflict:
        raise conflict  # Commit an authorized expiry transition, never change the answers.
    return result
