from fastapi import APIRouter, Depends, Request, Response

from app.api.polls import Identifier, no_store
from app.auth.dependencies import current_user, database
from app.auth.models import UserOut
from app.common.responses import Success, request_id
from app.meetings import service
from app.meetings.models import ConfirmIn, MeetingOut

router = APIRouter(prefix='/api/v1/polls', tags=['meetings'], dependencies=[Depends(no_store)])


@router.post('/{poll_id}/confirm', response_model=Success[MeetingOut], status_code=201)
def confirm(poll_id: Identifier, body: ConfirmIn, request: Request, response: Response,
            account: UserOut = Depends(current_user), engine=Depends(database)):
    value, created = service.confirm(engine, account.id, poll_id, body)
    response.status_code = 201 if created else 200
    return Success(data=value, request_id=request_id(request))


@router.get('/{poll_id}/meeting', response_model=Success[MeetingOut | None])
def existing(poll_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_for_poll(engine, account.id, poll_id), request_id=request_id(request))
