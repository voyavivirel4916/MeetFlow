from pydantic import BaseModel, Field, field_validator

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
