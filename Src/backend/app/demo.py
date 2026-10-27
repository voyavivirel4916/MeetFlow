"""Explicit disposable demo data; never seed an existing directory or the main database."""
import argparse
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


def seed(settings, *, member_count=4, slot_count=3, task_count=2):
    if settings.data_dir == Settings(_env_file=None).data_dir or settings.data_dir.exists():
        raise ValueError('Use a new, separate demo directory; existing directories are never modified.')
    if not 4 <= member_count <= 20 or not 3 <= slot_count <= 15 or not 0 <= task_count <= 200:
        raise ValueError('Unsupported demo dimensions.')
    upgrade(settings)
    engine = make_engine(database_path(settings))
    try:
        users = [auth.register(engine, RegisterIn(username='demo_owner' if i==0 else f'demo_member{i}',
                  email=f'demo{i}@example.com', password=PASSWORD)) for i in range(member_count)]
        lead=users[0].id
        group=groups.create_group(engine, lead, GroupIn(name='MeetFlow 独立演示小组',description='专用演示数据，可从未填写的排期开始体验。'))
        for user in users[1:]:groups.join_group(engine,user.id,group.invite_code)
        now=clock.now_ms()//60000*60000
        def poll(title):
            value=polls.create_draft(engine,lead,group.id,DraftIn(title=title,location='计算机大楼2015A',
                response_deadline=format_ms(now+86400000),participants=[{'user_id':user.id,'importance':'REQUIRED' if i<2 else 'NORMAL'} for i,user in enumerate(users)],
                slots=[{'start_at':format_ms(now+172800000+i*3600000),'end_at':format_ms(now+174600000+i*3600000)} for i in range(slot_count)]))
            return polls.transition_poll(engine,lead,value.id,'open')
        fresh=poll('从这里开始：四人空闲填写')
        completed=poll('已确认会议与行动示例')
        for index,user in enumerate(users):
            votes.save_votes(engine,user.id,completed.id,VotesIn(votes=[{'slot_id':slot.id,'availability':'AVAILABLE' if i==0 else ['AVAILABLE','MAYBE','UNAVAILABLE'][(index+i)%3]} for i,slot in enumerate(completed.slots)]))
        polls.transition_poll(engine,lead,completed.id,'close')
        meeting,_=meetings.confirm(engine,lead,completed.id,ConfirmIn(slot_id=completed.slots[0].id))
        meetings.update_meeting(engine,lead,meeting.id,MeetingUpdate(agenda='1. 核对推荐时间\n2. 明确下一步分工',minutes='共同确定首选时间，按分工推进并在任务列表跟进。'))
        for i in range(task_count):
            tasks.create_task(engine,lead,meeting.id,TaskIn(title=['核对前端交互','整理课程汇报'][i] if i<2 else f'性能样本任务{i+1:03}',
                description='独立演示任务',assignee_id=users[1+i%(len(users)-1)].id,due_at=format_ms(now+259200000+i*60000),client_request_id=str(uuid4())))
        return {'group_id':group.id,'open_poll_id':fresh.id,'confirmed_poll_id':completed.id,'meeting_id':meeting.id,
                'usernames':[user.username for user in users],'member_count':member_count,'slot_count':slot_count,'task_count':task_count}
    finally:engine.dispose()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True,help='New absolute directory; never the normal data directory.')
    args=parser.parse_args()
    if not args.data_dir.is_absolute():parser.error('Use an absolute path.')
    try:summary=seed(Settings(_env_file=None,data_dir=args.data_dir))
    except ValueError as error:parser.error(str(error))
    print('Demo created in the requested isolated directory.')
    print('Accounts: '+', '.join(summary['usernames']))
    print('Demo-only password: '+PASSWORD)
    print('Set MEETFLOW_DATA_DIR to this directory before starting the app on an unused local port.')


if __name__=='__main__':main()
