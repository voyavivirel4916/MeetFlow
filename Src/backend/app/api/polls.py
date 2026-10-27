from typing import Annotated
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.auth.dependencies import current_user, database
from app.auth.models import EmptyIn, UserOut
from app.common.responses import Success, request_id
from app.polls import service
from app.polls.models import DraftIn, PollOut, PollPage


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/api/v1', tags=['polls'], dependencies=[Depends(no_store)])
Identifier = Annotated[int, Path(ge=1, le=9223372036854775807)]


@router.post('/groups/{group_id}/polls', response_model=Success[PollOut], status_code=201)
def create(group_id: Identifier, body: DraftIn, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.create_draft(engine, account.id, group_id, body), request_id=request_id(request))


@router.get('/groups/{group_id}/polls', response_model=Success[PollPage])
def listing(group_id: Identifier, request: Request, page: Annotated[int, Query(ge=1)] = 1,
            page_size: Annotated[int, Query(ge=1, le=50)] = 20,
            view: Literal['current', 'history', 'trash'] = 'current',
            account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.list_polls(engine, account.id, group_id, page, page_size, view), request_id=request_id(request))


@router.get('/polls/{poll_id}', response_model=Success[PollOut])
def detail(poll_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_poll(engine, account.id, poll_id), request_id=request_id(request))


@router.put('/polls/{poll_id}', response_model=Success[PollOut])
def replace(poll_id: Identifier, body: DraftIn, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.replace_draft(engine, account.id, poll_id, body), request_id=request_id(request))


def register_action(action):
    def transition(poll_id: Identifier, body: EmptyIn, request: Request,
                   account: UserOut = Depends(current_user), engine=Depends(database)):
        return Success(data=service.transition_poll(engine, account.id, poll_id, action), request_id=request_id(request))
    transition.__name__ = f'{action}_poll'
    router.add_api_route(f'/polls/{{poll_id}}/{action}', transition, methods=['POST'], response_model=Success[PollOut])


for action in ['open', 'close', 'cancel']:
    register_action(action)


def register_organization(action):
    def organize(poll_id: Identifier, body: EmptyIn, request: Request,
                 account: UserOut = Depends(current_user), engine=Depends(database)):
        return Success(data=service.organize_poll(engine, account.id, poll_id, action), request_id=request_id(request))
    organize.__name__ = f'{action}_poll'
    router.add_api_route(f'/polls/{{poll_id}}/{action}', organize, methods=['POST'], response_model=Success[PollOut])


for action in ['delete', 'restore', 'archive', 'unarchive']:
    register_organization(action)
