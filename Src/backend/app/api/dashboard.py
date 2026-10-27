"""One consistent, permission-scoped snapshot for the personal workspace."""
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel
from sqlalchemy import select,func,and_

from app.auth.dependencies import current_user,database
from app.auth.models import UserOut
from app.api.polls import no_store
from app.common import clock
from app.common.responses import Success,request_id
from app.common.times import format_ms
from app.db.models import groups,group_members,polls,participants,slots,meetings,tasks
from app.tasks.models import TaskOut
from app.tasks.service import _out

router=APIRouter(prefix='/api/v1',tags=['dashboard'],dependencies=[Depends(no_store)])


class PollItem(BaseModel):
    id:int
    group_id:int
    group_name:str
    title:str
    response_deadline:str
    candidate_count:int
    submitted_count:int
    participant_count:int


class MeetingItem(BaseModel):
    id:int
    group_id:int
    group_name:str
    title:str
    location:str
    start_at:str
    end_at:str


class TaskItem(TaskOut):
    group_name:str


class GroupItem(BaseModel):
    id:int
    name:str
    owner_id:int
    member_count:int


class PollSection(BaseModel):
    total:int
    items:list[PollItem]


class MeetingSection(BaseModel):
    total:int
    items:list[MeetingItem]


class TaskSection(BaseModel):
    total:int
    items:list[TaskItem]


class GroupSection(BaseModel):
    total:int
    items:list[GroupItem]


class DashboardOut(BaseModel):
    generated_at:str
    pending_polls:PollSection
    upcoming_meetings:MeetingSection
    tasks:TaskSection
    groups:GroupSection


def snapshot(engine,actor):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        # Establish a read snapshot before sampling time, including after a blocked read.
        connection.execute(select(func.count()).select_from(group_members).where(group_members.c.user_id==actor)).scalar_one()
        now=clock.now_ms()
        member=select(group_members.c.user_id).where(group_members.c.group_id==groups.c.id,
                    group_members.c.user_id==actor).correlate(groups).exists()
        roster=participants.alias('all_participants')
        candidates=select(func.count()).select_from(slots).where(slots.c.poll_id==polls.c.id).correlate(polls).scalar_subquery()
        people=select(func.count()).select_from(roster).where(roster.c.poll_id==polls.c.id).correlate(polls).scalar_subquery()
        submitted=select(func.count()).select_from(roster).where(roster.c.poll_id==polls.c.id,roster.c.submitted_at.is_not(None)).correlate(polls).scalar_subquery()
        pending=select(polls.c.id,polls.c.group_id,groups.c.name.label('group_name'),polls.c.title,polls.c.response_deadline,
                       candidates.label('candidate_count'),people.label('participant_count'),submitted.label('submitted_count'))\
            .select_from(polls.join(groups,groups.c.id==polls.c.group_id).join(participants,participants.c.poll_id==polls.c.id))\
            .where(member,participants.c.user_id==actor,participants.c.submitted_at.is_(None),polls.c.status=='OPEN',
                   polls.c.response_deadline>now,polls.c.deleted_at.is_(None),polls.c.archived_at.is_(None))
        upcoming=select(meetings,groups.c.name.label('group_name')).select_from(meetings.join(groups,groups.c.id==meetings.c.group_id)
            .join(polls,polls.c.id==meetings.c.poll_id).join(participants,participants.c.poll_id==polls.c.id))\
            .where(member,participants.c.user_id==actor,polls.c.deleted_at.is_(None),meetings.c.end_at>now,
                   meetings.c.start_at<now+7*86400000)
        todo=select(tasks,groups.c.name.label('group_name')).select_from(tasks.join(groups,groups.c.id==tasks.c.group_id)
            .join(meetings,meetings.c.id==tasks.c.meeting_id).join(polls,polls.c.id==meetings.c.poll_id))\
            .where(member,tasks.c.assignee_id==actor,tasks.c.status.in_(['TODO','IN_PROGRESS']),polls.c.deleted_at.is_(None))
        member_count=select(func.count()).select_from(group_members).where(group_members.c.group_id==groups.c.id).correlate(groups).scalar_subquery()
        mygroups=select(groups.c.id,groups.c.name,groups.c.owner_id,member_count.label('member_count')).where(member)
        def section(query,order,convert):
            total=connection.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            rows=connection.execute(query.order_by(*order).limit(5)).mappings().all()
            return {'total':total,'items':[convert(row) for row in rows]}
        return DashboardOut(generated_at=format_ms(now),
            pending_polls=section(pending,[polls.c.response_deadline,polls.c.id],lambda row:PollItem(**dict(row,response_deadline=format_ms(row['response_deadline'])))),
            upcoming_meetings=section(upcoming,[meetings.c.start_at,meetings.c.id],lambda row:MeetingItem(**{k:row[k] for k in ['id','group_id','group_name','title','location']},start_at=format_ms(row['start_at']),end_at=format_ms(row['end_at']))),
            tasks=section(todo,[tasks.c.due_at,tasks.c.id],lambda row:TaskItem(**_out(row).model_dump(),group_name=row['group_name'])),
            groups=section(mygroups,[groups.c.created_at.desc(),groups.c.id.desc()],lambda row:GroupItem(**row)))


@router.get('/dashboard',response_model=Success[DashboardOut])
def dashboard(request:Request,account:UserOut=Depends(current_user),engine=Depends(database)):
    return Success(data=snapshot(engine,account.id),request_id=request_id(request))
