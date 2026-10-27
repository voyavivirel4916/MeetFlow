from pydantic import BaseModel


class RecommendationItem(BaseModel):
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
    conflict_user_ids: list[int]
    reason: str


class RecommendationOut(BaseModel):
    poll_id: int
    items: list[RecommendationItem]
