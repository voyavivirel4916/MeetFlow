import json
from sqlalchemy import and_, func, insert, select, update

from app.common import clock
from app.common.search import search_text
from app.common.responses import ApiError
from app.common.times import format_ms, to_ms
from app.db.connection import write_transaction
from app.db.models import group_members, tasks
from app.groups.service import require_member
from app.meetings.service import _require_meeting
from app.polls.service import _invalid
from app.tasks.models import TaskOut, TaskPage


def _out(row):
    fields = {key: row[key] for key in ['id', 'group_id', 'meeting_id', 'creator_id', 'assignee_id', 'title', 'description', 'status']}
    return TaskOut(**fields,version=row['version'], **{key: format_ms(row[key]) for key in ['due_at', 'created_at', 'updated_at']},
                   completed_at=None if row['completed_at'] is None else format_ms(row['completed_at']))


def create_task(engine, actor, meeting_id, data):
    # The immediate transaction serializes competing creation requests before lookup.
    with write_transaction(engine) as connection:
        meeting = _require_meeting(connection, actor, meeting_id, owner=True)
        existing = connection.execute(select(tasks).where(tasks.c.creator_id == actor, tasks.c.client_request_id == data.client_request_id)).mappings().first()
        fields = dict(meeting_id=meeting_id, assignee_id=data.assignee_id, title=data.title, description=data.description, due_at=to_ms(data.due_at))
        if existing is not None:
            original=json.loads(existing['creation_payload']) if existing['creation_payload'] else {key:existing[key] for key in fields}
            if original != fields:
                raise ApiError(409, 'STATE_CONFLICT', '同一次创建标识对应不同任务，请先核对原提交。')
            return _out(existing), False
        member = connection.execute(select(group_members.c.user_id).where(group_members.c.group_id == meeting['group_id'], group_members.c.user_id == data.assignee_id)).first()
        if member is None:
            raise _invalid('assignee_id', '执行人须为本小组成员。')
        now = clock.now_ms()
        if fields['due_at'] <= now:
            raise _invalid('due_at', '截止时间须晚于当前服务端时间。')
        identifier = connection.execute(insert(tasks).values(**fields, group_id=meeting['group_id'], creator_id=actor,
            status='TODO', completed_at=None, client_request_id=data.client_request_id, created_at=now, updated_at=now,
            version=1,creation_payload=json.dumps(fields,sort_keys=True,ensure_ascii=True))).inserted_primary_key[0]
        return _out(connection.execute(select(tasks).where(tasks.c.id == identifier)).mappings().one()), True


def _require_task(connection,actor,task_id):
    row=connection.execute(select(tasks).where(tasks.c.id==task_id)).mappings().first()
    if row is None:
        raise ApiError(404,'NOT_FOUND','未找到可访问的任务。')
    try:group=require_member(connection,actor,row['group_id'])
    except ApiError:raise ApiError(404,'NOT_FOUND','未找到可访问的任务。') from None
    return row,group


def _check_version(row,expected_version):
    if row['version']!=expected_version:
        raise ApiError(409,'VERSION_CONFLICT','任务已被更新，请读取最新内容后再操作。')
    if row['version']>=9007199254740991:
        raise ApiError(409,'STATE_CONFLICT','任务版本已到上限，请联系负责人。')


def change_status(engine, actor, task_id, status, expected_version):
    with write_transaction(engine) as connection:
        row,group=_require_task(connection,actor,task_id)
        if actor not in {group['owner_id'], row['assignee_id']}:
            raise ApiError(403, 'FORBIDDEN', '只有负责人或执行人可以修改任务状态。')
        if 'CANCELLED' in {status,row['status']}:
            if actor!=group['owner_id']:
                raise ApiError(403,'FORBIDDEN','只有负责人可以取消或恢复任务。')
            if (status=='CANCELLED' and row['status']=='DONE') or (row['status']=='CANCELLED' and status not in {'TODO','CANCELLED'}):
                raise ApiError(409,'STATE_CONFLICT','已完成任务须先重开；已取消任务只能恢复为待开始。')
        _check_version(row,expected_version)
        if row['status'] != status:
            now = max(clock.now_ms(), row['updated_at'])
            connection.execute(update(tasks).where(tasks.c.id == task_id).values(status=status,
                completed_at=now if status == 'DONE' else None, updated_at=now,version=row['version']+1))
        return _out(connection.execute(select(tasks).where(tasks.c.id == task_id)).mappings().one())


def edit_task(engine,actor,task_id,data):
    with write_transaction(engine) as connection:
        row,group=_require_task(connection,actor,task_id)
        if actor!=group['owner_id']:
            raise ApiError(403,'FORBIDDEN','只有负责人可以修改任务基本信息。')
        _check_version(row,data.expected_version)
        fields=data.model_dump(exclude_unset=True,exclude={'expected_version'})
        now=clock.now_ms()
        if 'due_at' in fields:
            fields['due_at']=to_ms(fields['due_at'])
            if fields['due_at']<=now:
                raise _invalid('due_at','新的截止时间须晚于当前服务端时间。')
            if fields['due_at']<=row['created_at']:
                raise _invalid('due_at','截止时间须晚于任务创建时间。')
        if 'assignee_id' in fields:
            member=connection.execute(select(group_members.c.user_id).where(
                group_members.c.group_id==row['group_id'],group_members.c.user_id==fields['assignee_id'])).first()
            if member is None:raise _invalid('assignee_id','执行人须为本小组成员。')
        if any(row[key]!=value for key,value in fields.items()):
            # Preserve the original input even for service-created legacy fixtures.
            original=row['creation_payload'] or json.dumps({key:row[key] for key in ['meeting_id','assignee_id','title','description','due_at']},sort_keys=True)
            connection.execute(update(tasks).where(tasks.c.id==task_id).values(**fields,
                updated_at=max(now,row['updated_at']),version=row['version']+1,creation_payload=original))
        return _out(connection.execute(select(tasks).where(tasks.c.id==task_id)).mappings().one())


def list_tasks(engine, actor, page, page_size, status=None, *, group_id=None, meeting_id=None, q=''):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        if group_id is not None:
            require_member(connection, actor, group_id)
            condition = tasks.c.group_id == group_id
        else:
            # Membership remains mandatory even for the personal view.
            condition = and_(tasks.c.assignee_id == actor, select(group_members.c.user_id).where(
                group_members.c.group_id == tasks.c.group_id, group_members.c.user_id == actor).exists())
            if status is None:
                condition = and_(condition, tasks.c.status.in_(['TODO','IN_PROGRESS']))
        if meeting_id is not None:
            meeting = _require_meeting(connection, actor, meeting_id)
            if meeting['group_id'] != group_id:
                raise _invalid('meeting_id', '会议须属于当前小组。')
            condition = and_(condition, tasks.c.meeting_id == meeting_id)
        if status is not None:
            condition = and_(condition, tasks.c.status == status)
        query=search_text(q)
        if query:condition=and_(condition,tasks.c.title.contains(query,autoescape=True))
        total = connection.execute(select(func.count()).select_from(tasks).where(condition)).scalar_one()
        offset = (page - 1) * page_size
        rows = [] if offset >= total else connection.execute(select(tasks).where(condition)
            .order_by(tasks.c.due_at, tasks.c.id).offset(offset).limit(page_size)).mappings().all()
        return TaskPage(items=[_out(row) for row in rows], page=page, page_size=page_size, total=total)
