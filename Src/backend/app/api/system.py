from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.common.responses import Success, request_id

router = APIRouter()


class LiveStatus(BaseModel):
    status: Literal['ok']


@router.get('/livez', response_model=Success[LiveStatus], tags=['bootstrap'],
            summary='T05启动探针；不代表数据库或业务就绪')
def live(request: Request):
    return Success(data=LiveStatus(status='ok'), request_id=request_id(request))
