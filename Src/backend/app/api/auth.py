from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import EmailStr, Field, field_validator

from app.auth import service
from app.auth.dependencies import current_user, database
from app.auth.models import EmptyIn, LoginIn, LogoutOut, RegisterIn, UserOut
from app.common.responses import Success, request_id
from app.common.responses import ApiError, InputModel
from app.auth import reset

router = APIRouter(prefix='/api/v1', tags=['auth'])


class ResetRequestIn(InputModel):
    email: EmailStr = Field(max_length=254)

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, value):
        return RegisterIn.normalize_email(value)

    @classmethod
    def normalized(cls, email):
        return str(email).strip().lower()


class ResetPasswordIn(InputModel):
    token: str = Field(min_length=1, max_length=128, strict=True)
    password: str = Field(min_length=8, max_length=128, strict=True)

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        return RegisterIn.not_blank(RegisterIn.valid_unicode(value))


@router.post('/auth/password-reset/request', status_code=202)
def request_reset(body: ResetRequestIn, request: Request, background: BackgroundTasks, engine=Depends(database)):
    settings = request.app.state.settings
    if not reset.configured(settings):
        raise ApiError(503, 'MAIL_UNAVAILABLE', '密码找回暂未开放，请联系小组负责人。')
    email = body.normalized(body.email)
    token = reset.issue(engine, email)
    if token:
        background.add_task(reset.deliver, settings, email, token)
    return Success(data={'message': '若该邮箱已注册，将收到重置邮件；请检查收件箱及垃圾邮件。'}, request_id=request_id(request))


@router.post('/auth/password-reset/confirm')
def confirm_reset(body: ResetPasswordIn, request: Request, engine=Depends(database)):
    reset.consume(engine, body.token, body.password)
    return Success(data={'message': '密码已重置，请重新登录。'}, request_id=request_id(request))


@router.post('/auth/register', response_model=Success[UserOut], status_code=201)
def register(body: RegisterIn, request: Request, response: Response, engine=Depends(database)):
    account = service.register(engine, body)
    request.state.user_id = account.id
    response.headers['Cache-Control'] = 'no-store'
    return Success(data=account, request_id=request_id(request))


@router.post('/auth/login', response_model=Success[UserOut])
def login(body: LoginIn, request: Request, response: Response, engine=Depends(database)):
    account, token = service.login(engine, body, request.cookies.get(service.COOKIE_NAME))
    response.set_cookie(service.COOKIE_NAME, token, max_age=service.SESSION_SECONDS,
                        path='/', httponly=True, samesite='strict', secure=request.app.state.settings.app_env == 'production')
    response.headers['Cache-Control'] = 'no-store'
    request.state.user_id = account.id
    return Success(data=account, request_id=request_id(request))


@router.post('/auth/logout', response_model=Success[LogoutOut])
def logout(body: EmptyIn, request: Request, response: Response, engine=Depends(database)):
    request.state.user_id = service.logout(engine, request.cookies.get(service.COOKIE_NAME))
    response.delete_cookie(service.COOKIE_NAME, path='/', httponly=True, samesite='strict',
                          secure=request.app.state.settings.app_env == 'production')
    response.headers['Cache-Control'] = 'no-store'
    return Success(data=LogoutOut(logged_out=True), request_id=request_id(request))


@router.get('/users/me', response_model=Success[UserOut])
def me(request: Request, response: Response, account: UserOut = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return Success(data=account, request_id=request_id(request))
