from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.common.responses import InputModel


class GroupIn(InputModel):
    name: str = Field(min_length=1, max_length=100, strict=True)
    description: str = Field(default='', max_length=10000, strict=True)

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('name', 'description')
    @classmethod
    def valid_unicode(cls, value):
        if '\x00' in value:
            raise ValueError('Text must not contain null characters.')
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ValueError('Use valid Unicode text.') from None
        return value


class JoinIn(InputModel):
    invite_code: str = Field(min_length=12, max_length=12, pattern=r'^[A-Z0-9]{12}$', strict=True)

    @field_validator('invite_code', mode='before')
    @classmethod
    def normalize_code(cls, value):
        # Only ASCII casing is accepted, not Unicode lookalikes that uppercase to ASCII.
        if isinstance(value, str):
            value = value.strip()
            if not value.isascii():
                raise ValueError('Use an ASCII invitation code.')
            return value.upper()
        return value


class GroupOut(BaseModel):
    id: int
    name: str
    description: str
    owner_id: int
    member_count: int
    invite_code: str | None = None
    invite_enabled: bool | None = None


class GroupPage(BaseModel):
    items: list[GroupOut]
    page: int
    page_size: int
    total: int


class MemberOut(BaseModel):
    user_id: int
    username: str
    role: Literal['OWNER', 'MEMBER']


class MemberList(BaseModel):
    items: list[MemberOut]


class InviteOut(BaseModel):
    invite_code: str
    invite_enabled: bool = True
