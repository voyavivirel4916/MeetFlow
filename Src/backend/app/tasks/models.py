from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.common.responses import InputModel
from app.polls.models import Timestamp, DraftIn

Status = Literal['TODO', 'IN_PROGRESS', 'DONE']


class TaskIn(InputModel):
    title: str = Field(strict=True, min_length=1, max_length=100)
    description: str = Field(default='', strict=True, max_length=10000)
    assignee_id: int = Field(strict=True, ge=1, le=9223372036854775807)
    due_at: Timestamp
    client_request_id: str = Field(strict=True)

    @field_validator('title', mode='before')
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('title', 'description')
    @classmethod
    def valid_text(cls, value):
        return DraftIn.valid_text(value)

    @field_validator('client_request_id')
    @classmethod
    def uuid_text(cls, value):
        return str(UUID(value))


class TaskStatusIn(InputModel):
    status: Status


class TaskOut(BaseModel):
    id: int
    group_id: int
    meeting_id: int
    creator_id: int
    assignee_id: int
    title: str
    description: str
    due_at: str
    status: Status
    completed_at: str | None
    created_at: str
    updated_at: str


class TaskPage(BaseModel):
    items: list[TaskOut]
    page: int
    page_size: int
    total: int
