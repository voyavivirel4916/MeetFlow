from fastapi import APIRouter, Depends, Request

from app.api.polls import Identifier, no_store
from app.auth.dependencies import current_user, database
from app.auth.models import UserOut
from app.common.responses import Success, request_id
from app.recommendations.models import RecommendationOut
from app.recommendations.service import get_recommendations

router = APIRouter(prefix='/api/v1/polls', tags=['recommendations'], dependencies=[Depends(no_store)])


@router.get('/{poll_id}/recommendations', response_model=Success[RecommendationOut])
def recommendations(poll_id: Identifier, request: Request, account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=get_recommendations(engine, account.id, poll_id), request_id=request_id(request))
