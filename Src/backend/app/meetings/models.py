from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.responses import InputModel


class ConfirmIn(InputModel):
    slot_id: int = Field(strict=True, ge=1, le=9223372036854775807)
    acknowledged: bool = Field(default=False, strict=True)
    selection_reason: str = Field(default='', strict=True, max_length=500)

    @field_validator('selection_reason', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('selection_reason')
    @classmethod
    def valid_text(cls, value):
        if '\x00' in value:
            raise ValueError('Invalid text.')
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ValueError('Use valid Unicode text.') from None
        return value


class MeetingOut(BaseModel):
    id: int
    poll_id: int
    group_id: int
    selected_slot_id: int
    title: str
    location: str
    start_at: str
    end_at: str
    selection_reason: str
    agenda: str
    minutes: str
    updated_at: str


class MeetingPage(BaseModel):
    items: list[MeetingOut]
    page: int
    page_size: int
    total: int


class MeetingUpdate(InputModel):
    agenda: str | None = Field(default=None, strict=True, max_length=10000)
    minutes: str | None = Field(default=None, strict=True, max_length=10000)

    @field_validator('agenda', 'minutes', mode='before')
    @classmethod
    def text_only(cls, value):
        if not isinstance(value, str):
            raise ValueError('Use plain text, not null.')
        return ConfirmIn.valid_text(value)

    @model_validator(mode='after')
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError('Provide agenda or minutes.')
        return self
