from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.common.responses import InputModel

Availability = Literal['AVAILABLE', 'MAYBE', 'UNAVAILABLE']


class VoteIn(InputModel):
    slot_id: int = Field(strict=True, ge=1, le=9223372036854775807)
    availability: Availability


class VotesIn(InputModel):
    votes: list[VoteIn] = Field(min_length=1, max_length=15)

    @model_validator(mode='after')
    def unique_slots(self):
        if len({item.slot_id for item in self.votes}) != len(self.votes):
            raise ValueError('Each candidate must appear exactly once.')
        return self


class VoteOut(BaseModel):
    slot_id: int
    availability: Availability


class VotesOut(BaseModel):
    poll_id: int
    submitted_at: str | None
    votes: list[VoteOut]
