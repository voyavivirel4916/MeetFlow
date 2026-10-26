from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.auth.dependencies import current_user, database
from app.auth.models import EmptyIn, UserOut
from app.common.responses import Success, request_id
from app.groups import service
from app.groups.models import GroupIn, GroupOut, GroupPage, InviteOut, JoinIn, MemberList


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/api/v1/groups', tags=['groups'], dependencies=[Depends(no_store)])
GroupId = Annotated[int, Path(ge=1, le=9223372036854775807)]


@router.post('', response_model=Success[GroupOut], response_model_exclude_none=True, status_code=201)
def create_group(body: GroupIn, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.create_group(engine, account.id, body), request_id=request_id(request))


@router.get('', response_model=Success[GroupPage], response_model_exclude_none=True)
def list_groups(request: Request, page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=50)] = 20,
                account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.list_groups(engine, account.id, page, page_size), request_id=request_id(request))


@router.post('/join', response_model=Success[GroupOut], response_model_exclude_none=True)
def join_group(body: JoinIn, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.join_group(engine, account.id, body.invite_code), request_id=request_id(request))


@router.get('/{group_id}', response_model=Success[GroupOut], response_model_exclude_none=True)
def get_group(group_id: GroupId, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_group(engine, account.id, group_id), request_id=request_id(request))


@router.get('/{group_id}/members', response_model=Success[MemberList])
def list_members(group_id: GroupId, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.list_members(engine, account.id, group_id), request_id=request_id(request))


@router.post('/{group_id}/invite-code/reset', response_model=Success[InviteOut])
def reset_invite(group_id: GroupId, body: EmptyIn, request: Request,
                 account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.reset_invite(engine, account.id, group_id), request_id=request_id(request))
