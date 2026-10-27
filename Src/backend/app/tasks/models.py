from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.responses import InputModel
from app.polls.models import Timestamp, DraftIn

Status = Literal['TODO', 'IN_PROGRESS', 'DONE', 'CANCELLED']


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
    expected_version: int = Field(strict=True,ge=1,le=9007199254740991)


class TaskUpdate(InputModel):
    expected_version: int = Field(strict=True,ge=1,le=9007199254740991)
    title: str | None = Field(default=None,strict=True,min_length=1,max_length=100)
    description: str | None = Field(default=None,strict=True,max_length=10000)
    assignee_id: int | None = Field(default=None,strict=True,ge=1,le=9223372036854775807)
    due_at: Timestamp | None = None

    @field_validator('title',mode='before')
    @classmethod
    def trim_title(cls,value):
        return TaskIn.trim_title(value)

    @field_validator('title','description')
    @classmethod
    def valid_text(cls,value):
        return TaskIn.valid_text(value) if value is not None else value

    @model_validator(mode='after')
    def nonempty(self):
        fields=self.model_fields_set-{'expected_version'}
        if not fields or any(getattr(self,key) is None for key in fields):
            raise ValueError('Provide at least one non-null editable field.')
        return self


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
    version: int


class TaskPage(BaseModel):
    items: list[TaskOut]
    page: int
    page_size: int
    total: int
