from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.common.responses import ApiError, Success, request_id
from app.common.config import ConfigurationError
from app.db.connection import require_current_schema

router = APIRouter()


class LiveStatus(BaseModel):
    status: Literal['ok']


@router.get('/livez', response_model=Success[LiveStatus], tags=['bootstrap'],
            summary='T05启动探针；不代表数据库或业务就绪')
def live(request: Request):
    return Success(data=LiveStatus(status='ok'), request_id=request_id(request))


@router.get('/api/v1/health', response_model=Success[LiveStatus], tags=['system'],
            summary='本机数据库可读且结构版本正确；无需登录')
def health(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        require_current_schema(request.app.state.settings)
    except ConfigurationError:
        raise ApiError(503, 'STORAGE_UNAVAILABLE', '本机存储暂时不可用，请检查数据库后重试。') from None
    return Success(data=LiveStatus(status='ok'), request_id=request_id(request))
