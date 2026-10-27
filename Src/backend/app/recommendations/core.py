"""Deterministic ranking; no database, network, clock or mutable input state."""
from dataclasses import dataclass, replace
from typing import Literal, Sequence

Importance = Literal['REQUIRED', 'NORMAL']
Availability = Literal['AVAILABLE', 'MAYBE', 'UNAVAILABLE']
_WEIGHTS = {'REQUIRED': 3, 'NORMAL': 1}
_VALUES = {'AVAILABLE': 2, 'MAYBE': 1, 'UNAVAILABLE': -2, None: 0}
REQUIRED_CONFLICT_PENALTY = 20
UNSUBMITTED_PENALTY = 2


@dataclass(frozen=True)
class Person:
    user_id: int
    importance: Importance


@dataclass(frozen=True)
class Candidate:
    id: int
    start_at: int  # UTC milliseconds, normalized by the wire/storage adapter.
    end_at: int


@dataclass(frozen=True)
class Answer:
    user_id: int
    slot_id: int
    availability: Availability | None


@dataclass(frozen=True)
class RankedSlot:
    slot_id: int
    rank: int
    base_score: int
    score: int
    required_unavailable_count: int
    required_unsubmitted_count: int
    required_maybe_count: int
    available_count: int
    maybe_count: int
    unavailable_count: int
    unsubmitted_count: int
    conflict_user_ids: tuple[int, ...]
    reason: str


def _positive(value):
    return type(value) is int and value > 0


def _validate(people, candidates, answers):
    if not 1 <= len(people) <= 20 or not 1 <= len(candidates) <= 15:
        raise ValueError('Require 1-20 participants and 1-15 candidates.')
    if any(not _positive(person.user_id) or not isinstance(person.importance, str) or person.importance not in _WEIGHTS for person in people):
        raise ValueError('Invalid participant.')
    if any(not _positive(slot.id) or type(slot.start_at) is not int or type(slot.end_at) is not int or slot.start_at >= slot.end_at for slot in candidates):
        raise ValueError('Invalid candidate or time order.')
    people_ids, slot_ids = {person.user_id for person in people}, {slot.id for slot in candidates}
    if len(people_ids) != len(people) or len(slot_ids) != len(candidates):
        raise ValueError('Duplicate participant or candidate.')
    seen = set()
    for answer in answers:
        pair = (answer.user_id, answer.slot_id)
        if not _positive(answer.user_id) or not _positive(answer.slot_id) or answer.user_id not in people_ids or answer.slot_id not in slot_ids or (answer.availability is not None and (not isinstance(answer.availability, str) or answer.availability not in _VALUES)) or pair in seen:
            raise ValueError('Invalid, foreign or duplicate answer.')
        seen.add(pair)


def _reason(item, required_count, participant_count):
    text = (f'有空{item.available_count}人，勉强{item.maybe_count}人，没空{item.unavailable_count}人，未填{item.unsubmitted_count}人。'
            f'基础分{item.base_score}，必到冲突扣分{REQUIRED_CONFLICT_PENALTY * item.required_unavailable_count}，'
            f'未填扣分{UNSUBMITTED_PENALTY * item.unsubmitted_count}，最终分{item.score}。')
    if item.required_unavailable_count:
        text += f'必到成员有{item.required_unavailable_count}人没空。'
    if item.required_unsubmitted_count:
        text += f'必到成员有{item.required_unsubmitted_count}人未填，出席情况尚未确定。'
    if item.required_maybe_count:
        text += f'必到成员有{item.required_maybe_count}人勉强，需要协调。'
    if not required_count:
        text += '未设置必到成员。'
    elif not (item.required_unavailable_count or item.required_unsubmitted_count or item.required_maybe_count):
        text += '必到成员均已填写有空。'
    if item.available_count == participant_count:
        text += '所有参与者均已填写有空。'
    return text


def rank_slots(participants: Sequence[Person], slots: Sequence[Candidate], votes: Sequence[Answer]) -> list[RankedSlot]:
    _validate(participants, slots, votes)
    people = sorted(participants, key=lambda person: person.user_id)
    answers = {(answer.user_id, answer.slot_id): answer.availability for answer in votes}
    pending = []
    required_count = sum(person.importance == 'REQUIRED' for person in people)
    for slot in slots:
        counts = {'AVAILABLE': 0, 'MAYBE': 0, 'UNAVAILABLE': 0, None: 0}
        required = {'MAYBE': 0, 'UNAVAILABLE': 0, None: 0}
        base_score, conflicts = 0, []
        for person in people:
            value = answers.get((person.user_id, slot.id))
            counts[value] += 1
            base_score += _WEIGHTS[person.importance] * _VALUES[value]
            if person.importance == 'REQUIRED' and value != 'AVAILABLE':
                required[value] += 1
            if value == 'UNAVAILABLE':
                conflicts.append(person.user_id)
        item = RankedSlot(slot_id=slot.id, rank=0, base_score=base_score,
            score=base_score-REQUIRED_CONFLICT_PENALTY*required['UNAVAILABLE']-UNSUBMITTED_PENALTY*counts[None],
            required_unavailable_count=required['UNAVAILABLE'], required_unsubmitted_count=required[None], required_maybe_count=required['MAYBE'],
            available_count=counts['AVAILABLE'], maybe_count=counts['MAYBE'], unavailable_count=counts['UNAVAILABLE'],
            unsubmitted_count=counts[None], conflict_user_ids=tuple(conflicts), reason='')
        key = (item.required_unavailable_count, -item.score, -item.available_count, slot.start_at, slot.end_at, slot.id)
        pending.append((key, item))
    all_conflicted = all(item.unavailable_count > 0 for _key, item in pending)
    return [replace(item, rank=index, reason=_reason(item, required_count, len(people)) +
        ('所有候选时段均有成员没空，排名不代表全员可参加。' if all_conflicted else ''))
        for index, (_key, item) in enumerate(sorted(pending, key=lambda pair: pair[0]), 1)]
