from fastapi import APIRouter, Depends, Request, Response

from app.auth import service
from app.auth.dependencies import current_user, database
from app.auth.models import EmptyIn, LoginIn, LogoutOut, RegisterIn, UserOut
from app.common.responses import Success, request_id

router = APIRouter(prefix='/api/v1', tags=['auth'])


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
                        path='/', httponly=True, samesite='strict', secure=False)
    response.headers['Cache-Control'] = 'no-store'
    request.state.user_id = account.id
    return Success(data=account, request_id=request_id(request))


@router.post('/auth/logout', response_model=Success[LogoutOut])
def logout(body: EmptyIn, request: Request, response: Response, engine=Depends(database)):
    request.state.user_id = service.logout(engine, request.cookies.get(service.COOKIE_NAME))
    response.delete_cookie(service.COOKIE_NAME, path='/', httponly=True, samesite='strict', secure=False)
    response.headers['Cache-Control'] = 'no-store'
    return Success(data=LogoutOut(logged_out=True), request_id=request_id(request))


@router.get('/users/me', response_model=Success[UserOut])
def me(request: Request, response: Response, account: UserOut = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return Success(data=account, request_id=request_id(request))
