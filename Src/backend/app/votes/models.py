from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.common.responses import InputModel
from app.polls.models import ParticipantOut, SlotOut, Status

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


class Counts(BaseModel):
    available_count: int = 0
    maybe_count: int = 0
    unavailable_count: int = 0
    unanswered_count: int = 0


class MatrixParticipant(ParticipantOut, Counts):
    pass


class MatrixSlot(SlotOut, Counts):
    pass


class MatrixCell(BaseModel):
    user_id: int
    slot_id: int
    availability: Availability | None


class Progress(BaseModel):
    participant_count: int
    submitted_count: int
    unsubmitted_count: int


class MatrixOut(BaseModel):
    poll_id: int
    effective_status: Status
    participants: list[MatrixParticipant]
    slots: list[MatrixSlot]
    cells: list[MatrixCell]
    progress: Progress
