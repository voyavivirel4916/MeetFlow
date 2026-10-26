from typing import Any, Generic, TypeVar

from fastapi import Request
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse

T = TypeVar('T')


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Success(BaseModel, Generic[T]):
    data: T
    request_id: str


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(request_id: str, status: int, code: str, message: str,
                   details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={'error': {'code': code, 'message': message, 'details': details or {}}, 'request_id': request_id},
        headers={'X-Request-ID': request_id},
    )


def request_id(request: Request) -> str:
    return request.state.request_id
