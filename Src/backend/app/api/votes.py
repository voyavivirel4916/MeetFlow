from fastapi import APIRouter, Depends, Request

from app.api.polls import Identifier, no_store
from app.auth.dependencies import current_user, database
from app.auth.models import UserOut
from app.common.responses import Success, request_id
from app.votes import service
from app.votes.models import MatrixOut, VotesIn, VotesOut

router = APIRouter(prefix='/api/v1/polls', tags=['votes'], dependencies=[Depends(no_store)])


@router.get('/{poll_id}/matrix', response_model=Success[MatrixOut])
def matrix(poll_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_matrix(engine, account.id, poll_id), request_id=request_id(request))


@router.get('/{poll_id}/votes/me', response_model=Success[VotesOut])
def detail(poll_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.get_votes(engine, account.id, poll_id), request_id=request_id(request))


@router.put('/{poll_id}/votes/me', response_model=Success[VotesOut])
def replace(poll_id: Identifier, body: VotesIn, request: Request,
            account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.save_votes(engine, account.id, poll_id, body), request_id=request_id(request))
