from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.system import router
from app.api.auth import router as auth_router
from app.api.groups import router as groups_router
from app.api.polls import router as polls_router
from app.api.votes import router as votes_router
from app.api.recommendations import router as recommendations_router
from app.api.meetings import router as meetings_router
from app.common.config import Settings, load_settings, prepare_runtime
from app.common.middleware import RequestContextMiddleware
from app.common.responses import ApiError, error_response, request_id
from app.db.connection import require_current_schema
from app.web import check_frontend, install_frontend


def validate_runtime(settings: Settings):
    prepare_runtime(settings)
    require_current_schema(settings, writable=True)
    check_frontend(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        validate_runtime(config)
        yield

    app = FastAPI(title='MeetFlow', version='0.1.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url='/openapi.json')
    app.state.settings = config
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return error_response(request_id(request), error.status, error.code, error.message, error.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        fields = [{'location': list(item['loc']), 'type': item['type']} for item in error.errors()]
        return error_response(request_id(request), 422, 'VALIDATION_ERROR', '请检查填写内容。', {'fields': fields})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        codes = {400:'INVALID_INPUT',401:'UNAUTHENTICATED',403:'FORBIDDEN',404:'NOT_FOUND',
                 405:'INVALID_INPUT',409:'STATE_CONFLICT',413:'PAYLOAD_TOO_LARGE',
                 422:'VALIDATION_ERROR',503:'STORAGE_UNAVAILABLE'}
        messages = {404:'未找到可访问的资源。',405:'请求方法不受支持。'}
        response = error_response(request_id(request), error.status_code,
                                  codes.get(error.status_code, 'INTERNAL_ERROR'),
                                  messages.get(error.status_code, '请求未能完成。'))
        for name, value in (error.headers or {}).items():
            if name.lower() in {'allow', 'www-authenticate', 'retry-after'}:
                response.headers[name] = value
        return response

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(groups_router)
    app.include_router(polls_router)
    app.include_router(votes_router)
    app.include_router(recommendations_router)
    app.include_router(meetings_router)
    install_frontend(app, config)
    return app
