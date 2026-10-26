from pydantic import BaseModel, EmailStr, Field, field_validator

from app.common.responses import InputModel


class LoginIn(InputModel):
    username: str = Field(min_length=1, max_length=32, strict=True)
    password: str = Field(min_length=1, max_length=128, strict=True)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator('password')
    @classmethod
    def valid_unicode(cls, value):
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ValueError('Password must contain valid Unicode characters.') from None
        return value


class RegisterIn(LoginIn):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-z0-9_]+$', strict=True)
    password: str = Field(min_length=8, max_length=128, strict=True)
    email: EmailStr = Field(max_length=254)

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            value = value.strip().lower()
            if '<' in value or '>' in value:
                raise ValueError('Use an email address without a display name.')
        return value

    @field_validator('password')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Password must not be blank.')
        return value


class EmptyIn(InputModel):
    pass


class UserOut(BaseModel):
    id: int
    username: str
    email: str


class LogoutOut(BaseModel):
    logged_out: bool
