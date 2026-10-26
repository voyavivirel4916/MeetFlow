import sqlite3

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError

from app.auth import service
from app.auth.models import UserOut
from app.common.responses import ApiError
from app.db.connection import database_path, make_engine


def database(request: Request):
    engine = make_engine(database_path(request.app.state.settings))
    try:
        yield engine
    except SQLAlchemyError as error:
        code = getattr(getattr(error, 'orig', None), 'sqlite_errorcode', 0) or 0
        if (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise ApiError(503, 'DB_BUSY', '本机数据库繁忙，请稍后核对并重试。') from None
        raise ApiError(503, 'STORAGE_UNAVAILABLE', '本机存储暂时不可用，请稍后重试。') from None
    finally:
        engine.dispose()


def current_user(request: Request, engine=Depends(database)) -> UserOut:
    account = service.authenticate(engine, request.cookies.get(service.COOKIE_NAME))
    request.state.user_id = account.id
    return account
