from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from app.common.responses import InputModel
from app.common.times import parse_rfc3339

Timestamp = Annotated[datetime, BeforeValidator(parse_rfc3339)]
Status = Literal['DRAFT', 'OPEN', 'CLOSED', 'CONFIRMED', 'CANCELLED']


class ParticipantIn(InputModel):
    user_id: int = Field(strict=True, ge=1, le=9223372036854775807)
    importance: Literal['REQUIRED', 'NORMAL']


class SlotIn(InputModel):
    start_at: Timestamp
    end_at: Timestamp

    @model_validator(mode='after')
    def ordered(self):
        if self.start_at >= self.end_at:
            raise ValueError('Start must precede end after millisecond normalization.')
        return self


class DraftIn(InputModel):
    title: str = Field(strict=True, min_length=1, max_length=100)
    description: str = Field(default='', strict=True, max_length=10000)
    location: str = Field(default='', strict=True, max_length=200)
    response_deadline: Timestamp
    participants: list[ParticipantIn]
    slots: list[SlotIn]

    @field_validator('title', mode='before')
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('title', 'description', 'location')
    @classmethod
    def valid_text(cls, value):
        if '\x00' in value:
            raise ValueError('Text must not contain null characters.')
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ValueError('Use valid Unicode text.') from None
        return value

    @model_validator(mode='after')
    def unique_children(self):
        if len({item.user_id for item in self.participants}) != len(self.participants):
            raise ValueError('A participant must appear only once.')
        if len({(item.start_at, item.end_at) for item in self.slots}) != len(self.slots):
            raise ValueError('A candidate time must appear only once.')
        return self


class ParticipantOut(BaseModel):
    user_id: int
    username: str
    importance: Literal['REQUIRED', 'NORMAL']
    submitted_at: str | None


class SlotOut(BaseModel):
    id: int
    start_at: str
    end_at: str


class PollOut(BaseModel):
    id: int
    group_id: int
    title: str
    description: str
    location: str
    response_deadline: str
    status: Status
    effective_status: Status
    participants: list[ParticipantOut]
    slots: list[SlotOut]
    updated_at: str


class PollPage(BaseModel):
    items: list[PollOut]
    page: int
    page_size: int
    total: int
