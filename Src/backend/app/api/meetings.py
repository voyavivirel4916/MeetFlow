from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.polls import Identifier, no_store
from app.auth.dependencies import current_user, database
from app.auth.models import UserOut
from app.common.responses import Success, request_id
from app.meetings import service
from app.meetings.models import ConfirmIn, MeetingOut, MeetingPage, MeetingUpdate

router = APIRouter(prefix='/api/v1/polls', tags=['meetings'], dependencies=[Depends(no_store)])
details_router = APIRouter(prefix='/api/v1', tags=['meetings'], dependencies=[Depends(no_store)])


@router.post('/{poll_id}/confirm', response_model=Success[MeetingOut], status_code=201)
def confirm(poll_id: Identifier, body: ConfirmIn, request: Request, response: Response,
            account: UserOut = Depends(current_user), engine=Depends(database)):
    value, created = service.confirm(engine, account.id, poll_id, body)
    response.status_code = 201 if created else 200
    return Success(data=value, request_id=request_id(request))


@router.get('/{poll_id}/meeting', response_model=Success[MeetingOut | None])
def existing(poll_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_for_poll(engine, account.id, poll_id), request_id=request_id(request))


@details_router.get('/meetings/{meeting_id}', response_model=Success[MeetingOut])
def get_meeting(meeting_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_meeting(engine, account.id, meeting_id), request_id=request_id(request))


@details_router.get('/groups/{group_id}/meetings', response_model=Success[MeetingPage])
def list_meetings(group_id: Identifier, request: Request, page: Annotated[int, Query(ge=1)] = 1,
                  page_size: Annotated[int, Query(ge=1, le=50)] = 20,
                  account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.list_meetings(engine, account.id, group_id, page, page_size), request_id=request_id(request))


@details_router.patch('/meetings/{meeting_id}', response_model=Success[MeetingOut])
def update_meeting(meeting_id: Identifier, body: MeetingUpdate, request: Request,
                   account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.update_meeting(engine, account.id, meeting_id, body), request_id=request_id(request))
