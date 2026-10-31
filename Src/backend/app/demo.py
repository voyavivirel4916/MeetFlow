"""Explicit disposable demo data; never seed an existing directory or the main database."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.common import clock
from app.common.config import Settings
from app.common.times import format_ms
from app.db.connection import database_path, make_engine
from app.db.migrate import upgrade
from app.auth import service as auth
from app.auth.models import RegisterIn
from app.groups import service as groups
from app.groups.models import GroupIn
from app.polls import service as polls
from app.polls.models import DraftIn
from app.votes import service as votes
from app.votes.models import VotesIn
from app.meetings import service as meetings
from app.meetings.models import ConfirmIn, MeetingUpdate
from app.tasks import service as tasks
from app.tasks.models import TaskIn

PASSWORD = 'MeetFlowDemo2026!'
BEIJING = timezone(timedelta(hours=8))


def showcase_anchor(presentation_date, actual_ms):
    """Keep real clocks intact; move only fictional schedule dates."""
    if presentation_date is None:
        return actual_ms // 60000 * 60000
    today = datetime.fromtimestamp(actual_ms / 1000, BEIJING).date()
    if not isinstance(presentation_date, date) or not today <= presentation_date <= today + timedelta(days=365):
        raise ValueError('Presentation date must be today or within the next 365 days (Beijing time).')
    planned = int(datetime.combine(presentation_date, time(10), BEIJING).timestamp() * 1000)
    return max(actual_ms // 60000 * 60000, planned)


def seed(settings, *, member_count=4, slot_count=3, task_count=2, showcase=False, presentation_date=None):
    if settings.app_env == 'production' or settings.data_dir == Settings(_env_file=None).data_dir or settings.data_dir.exists():
        raise ValueError('Use a new, separate demo directory; existing directories are never modified.')
    if not 4 <= member_count <= 20 or not 3 <= slot_count <= 15 or not 0 <= task_count <= 200:
        raise ValueError('Unsupported demo dimensions.')
    if presentation_date is not None and not showcase:
        raise ValueError('Presentation date is only supported for the rich showcase.')
    now = showcase_anchor(presentation_date, clock.now_ms())
    upgrade(settings)
    engine = make_engine(database_path(settings))
    try:
        users = [auth.register(engine, RegisterIn(username='demo_owner' if i==0 else f'demo_member{i}',
                  email=f'demo{i}@example.com', password=PASSWORD)) for i in range(member_count)]
        lead=users[0].id
        group=groups.create_group(engine, lead, GroupIn(name='软件工程课程小组 · 演示' if showcase else 'MeetFlow 独立演示小组',description='专用虚构示例，可自由体验排期、会议和任务；不涉及真实小组。'))
        for user in users[1:]:groups.join_group(engine,user.id,group.invite_code)
        def poll(title, *, publish=True, group_id=group.id):
            value=polls.create_draft(engine,lead,group_id,DraftIn(title=title,location='计算机大楼2015A',
                response_deadline=format_ms(now+86400000),participants=[{'user_id':user.id,'importance':'REQUIRED' if i<2 else 'NORMAL'} for i,user in enumerate(users)],
                slots=[{'start_at':format_ms(now+172800000+i*3600000),'end_at':format_ms(now+174600000+i*3600000)} for i in range(slot_count)]))
            return polls.transition_poll(engine,lead,value.id,'open') if publish else value
        fresh=poll('从这里开始：四人空闲填写')
        completed=poll('已确认会议与行动示例')
        for index,user in enumerate(users):
            votes.save_votes(engine,user.id,completed.id,VotesIn(votes=[{'slot_id':slot.id,'availability':'AVAILABLE' if i==0 else ['AVAILABLE','MAYBE','UNAVAILABLE'][(index+i)%3]} for i,slot in enumerate(completed.slots)]))
        polls.transition_poll(engine,lead,completed.id,'close')
        meeting,_=meetings.confirm(engine,lead,completed.id,ConfirmIn(slot_id=completed.slots[0].id))
        meetings.update_meeting(engine,lead,meeting.id,MeetingUpdate(agenda='1. 核对推荐时间\n2. 明确下一步分工',minutes='共同确定首选时间，按分工推进并在任务列表跟进。'))
        for i in range(0 if showcase else task_count):
            tasks.create_task(engine,lead,meeting.id,TaskIn(title=['核对前端交互','整理课程汇报'][i] if i<2 else f'性能样本任务{i+1:03}',
                description='独立演示任务',assignee_id=users[1+i%(len(users)-1)].id,due_at=format_ms(now+259200000+i*60000),client_request_id=str(uuid4())))
        examples={}
        if showcase:
            examples=_showcase(engine,users,group,fresh,completed,meeting,poll,now)
        return {'group_id':group.id,'open_poll_id':fresh.id,'confirmed_poll_id':completed.id,'meeting_id':meeting.id,
                'usernames':[user.username for user in users],'member_count':member_count,'slot_count':slot_count,'task_count':task_count,**examples}
    finally:engine.dispose()


def _showcase(engine, users, group, fresh, completed, meeting, poll, now):
    lead=users[0].id
    def answer(value,user,states):
        votes.save_votes(engine,user.id,value.id,VotesIn(votes=[
            {'slot_id':slot.id,'availability':states[i%len(states)]} for i,slot in enumerate(value.slots)]))
    for user in users[1:]:answer(fresh,user,['MAYBE','AVAILABLE','UNAVAILABLE'])
    unknown=poll('接口评审：关键成员尚未填写')
    answer(unknown,users[0],['AVAILABLE'])
    for user in users[2:]:answer(unknown,user,['AVAILABLE','MAYBE','UNAVAILABLE'])
    conflict=poll('技术讨论：所有候选均有必到冲突')
    for user in users:answer(conflict,user,['UNAVAILABLE'])
    polls.transition_poll(engine,lead,conflict.id,'close')
    poll('本周技术交流 · 草稿',publish=False)
    cancelled=poll('临时碰面 · 已取消')
    polls.transition_poll(engine,lead,cancelled.id,'cancel')
    deleted=poll('旧版原型讨论 · 回收站',publish=False)
    polls.organize_poll(engine,lead,deleted.id,'delete')
    history=poll('第一版验收 · 已归档')
    for user in users:answer(history,user,['AVAILABLE'])
    polls.transition_poll(engine,lead,history.id,'close')
    archived,_=meetings.confirm(engine,lead,history.id,ConfirmIn(slot_id=history.slots[0].id))
    meetings.update_meeting(engine,lead,archived.id,MeetingUpdate(agenda='核对第一版交付',minutes='演示归档后会议记录和任务仍然保留。'))
    polls.organize_poll(engine,lead,history.id,'archive')
    second=groups.create_group(engine,lead,GroupIn(name='课程汇报小组 · 演示',description='汇报材料与演示准备，均为虚构示例。'))
    for user in users[1:]:groups.join_group(engine,user.id,second.invite_code)
    presentation=poll('阶段汇报准备',group_id=second.id)
    for user in users:answer(presentation,user,['AVAILABLE'])
    polls.transition_poll(engine,lead,presentation.id,'close')
    report,_=meetings.confirm(engine,lead,presentation.id,ConfirmIn(slot_id=presentation.slots[0].id))
    meetings.update_meeting(engine,lead,report.id,MeetingUpdate(agenda='1. 确认汇报分工\n2. 排练演示',minutes='负责人准备演示，成员整理报告和截图。'))
    samples=[('整理接口测试中的异常场景','TODO',lead,meeting.id),
        ('核对排期归档与任务保留规则','IN_PROGRESS',lead,meeting.id),
        ('准备下次汇报的演示数据','TODO',lead,report.id),
        ('整理第一版测试报告','DONE',lead,meeting.id),
        ('制作复杂任务看板','CANCELLED',lead,meeting.id),
        ('检查窄窗口下的页面排版','IN_PROGRESS',users[1].id,meeting.id),
        ('准备课程汇报提纲','TODO',users[1].id,report.id),
        ('补充会议讨论结论','DONE',users[2].id,meeting.id),
        ('核对测试截图与文档链接','TODO',users[3].id,meeting.id),
        ('归档会议遗留事项跟进','TODO',lead,archived.id)]
    for i,(title,status,assignee,meeting_id) in enumerate(samples):
        task,_=tasks.create_task(engine,lead,meeting_id,TaskIn(title=title,description='虚构演示任务，可编辑、完成、取消或恢复。',
            assignee_id=assignee,due_at=format_ms(now+259200000+i*3600000),client_request_id=str(uuid4())))
        if status!='TODO':tasks.change_status(engine,lead,task.id,status,task.version)
    return {'task_count':len(samples),'poll_count':9,'group_count':2}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True,help='New absolute directory; never the normal data directory.')
    parser.add_argument('--showcase',action='store_true',help='Rich second-version examples: two groups, nine polls and ten tasks.')
    parser.add_argument('--presentation-date',type=date.fromisoformat,help='Beijing demonstration date, YYYY-MM-DD; requires --showcase.')
    args=parser.parse_args()
    if not args.data_dir.is_absolute():parser.error('Use an absolute path.')
    try:summary=seed(Settings(_env_file=None,data_dir=args.data_dir),showcase=args.showcase,presentation_date=args.presentation_date)
    except ValueError as error:parser.error(str(error))
    print('Demo created in the requested isolated directory.')
    print('Accounts: '+', '.join(summary['usernames']))
    print('Demo-only password: '+PASSWORD)
    print('Set MEETFLOW_DATA_DIR to this directory before starting the app on an unused local port.')


if __name__=='__main__':main()
