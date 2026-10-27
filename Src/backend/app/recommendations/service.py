from dataclasses import asdict

from app.common.responses import ApiError
from app.common.times import parse_rfc3339, to_ms
from app.recommendations.core import Answer, Candidate, Person, rank_slots
from app.recommendations.models import RecommendationItem, RecommendationOut
from app.votes.service import get_matrix


def get_recommendations(engine, user_id, poll_id):
    # All inputs come from one authorized read snapshot; never reuse cached scores.
    matrix = get_matrix(engine, user_id, poll_id)
    if matrix.effective_status not in {'OPEN', 'CLOSED', 'CONFIRMED'}:
        raise ApiError(409, 'STATE_CONFLICT', '草稿或已取消的排期不能生成推荐。')
    try:
        items = rank_slots([Person(person.user_id, person.importance) for person in matrix.participants],
            [Candidate(slot.id, to_ms(parse_rfc3339(slot.start_at)), to_ms(parse_rfc3339(slot.end_at))) for slot in matrix.slots],
            [Answer(cell.user_id, cell.slot_id, cell.availability) for cell in matrix.cells])
    except ValueError:
        raise ApiError(422, 'VALIDATION_ERROR', '排期参与者或候选数据不完整，无法生成推荐。') from None
    return RecommendationOut(poll_id=poll_id, items=[RecommendationItem(**asdict(item)) for item in items])
