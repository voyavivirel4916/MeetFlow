from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.polls import Identifier, no_store
from app.auth.dependencies import current_user, database
from app.auth.models import UserOut
from app.common.responses import Success, request_id
from app.tasks import service
from app.tasks.models import Status, TaskIn, TaskOut, TaskPage, TaskStatusIn, TaskUpdate

router = APIRouter(prefix='/api/v1', tags=['tasks'], dependencies=[Depends(no_store)])
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=50)]


@router.post('/meetings/{meeting_id}/tasks', response_model=Success[TaskOut], status_code=201)
def create(meeting_id: Identifier, body: TaskIn, request: Request, response: Response,
           account: UserOut = Depends(current_user), engine=Depends(database)):
    value, created = service.create_task(engine, account.id, meeting_id, body)
    response.status_code = 201 if created else 200
    return Success(data=value, request_id=request_id(request))


@router.patch('/tasks/{task_id}/status', response_model=Success[TaskOut])
def change(task_id: Identifier, body: TaskStatusIn, request: Request,
           account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.change_status(engine, account.id, task_id, body.status,body.expected_version), request_id=request_id(request))


@router.patch('/tasks/{task_id}',response_model=Success[TaskOut])
def edit(task_id:Identifier,body:TaskUpdate,request:Request,
         account:UserOut=Depends(current_user),engine=Depends(database)):
    return Success(data=service.edit_task(engine,account.id,task_id,body),request_id=request_id(request))


@router.get('/tasks/mine', response_model=Success[TaskPage])
def mine(request: Request, page: Page = 1, page_size: Size = 20, status: Status | None = None,
         account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.list_tasks(engine, account.id, page, page_size, status), request_id=request_id(request))


@router.get('/groups/{group_id}/tasks', response_model=Success[TaskPage])
def group_tasks(group_id: Identifier, request: Request, page: Page = 1, page_size: Size = 20, status: Status | None = None,
                meeting_id: Annotated[int | None, Query(ge=1, le=9223372036854775807)] = None,
                account: UserOut = Depends(current_user), engine=Depends(database)):
    return Success(data=service.list_tasks(engine, account.id, page, page_size, status, group_id=group_id, meeting_id=meeting_id), request_id=request_id(request))
