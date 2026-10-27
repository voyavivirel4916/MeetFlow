import sqlite3
import pytest
from app.db.connection import database_path
from test_bootstrap import assert_error
from test_groups import owner,other,create,data
from test_polls import setup,create_poll,draft,NOW
from test_votes import opened,answers
from test_meetings import closed,confirm,path
from test_meeting_content import meeting
from test_tasks import body,create_task


def dashboard(browser):
    response=browser.get('/api/v1/dashboard')
    assert response.headers['cache-control']=='no-store'
    return data(response)


def test_authentication_and_empty_dashboard(client,owner):
    from fastapi.testclient import TestClient
    with TestClient(client.app,base_url='http://127.0.0.1') as anonymous:
        assert_error(anonymous.get('/api/v1/dashboard'),401,'UNAUTHENTICATED')
    value=dashboard(owner)
    for key in ['pending_polls','upcoming_meetings','tasks','groups']:
        assert value[key]=={'total':0,'items':[]}


def test_pending_only_unsubmitted_active_participants(owner,other,opened):
    poll,now=opened
    first=dashboard(owner)
    assert first['pending_polls']['total']==1
    item=first['pending_polls']['items'][0]
    assert item['id']==poll['id'] and item['candidate_count']==len(poll['slots'])
    assert item['participant_count']==2 and item['submitted_count']==0
    assert 'invite_code' not in first['groups']['items'][0]
    data(owner.put(path(poll)+'/votes/me',json=answers(poll)))
    assert dashboard(owner)['pending_polls']['total']==0
    assert dashboard(other)['pending_polls']['items'][0]['submitted_count']==1
    now[0]+=60000
    assert dashboard(other)['pending_polls']['total']==0


def test_private_groups_and_nonparticipants_do_not_leak(owner,other,setup):
    group,_=setup
    poll=data(create_poll(owner,group,draft(participants=[{'user_id':1,'importance':'REQUIRED'}])),201)
    data(owner.post(path(poll)+'/open',json={}))
    assert dashboard(other)['pending_polls']['total']==0
    private=data(create(other),201)
    privatepoll=data(create_poll(other,private,draft(participants=[{'user_id':2,'importance':'REQUIRED'}])),201)
    data(other.post(path(privatepoll)+'/open',json={}))
    own=dashboard(owner)
    assert own['groups']['total']==1
    assert own['pending_polls']['total']==1 and own['pending_polls']['items'][0]['group_id']==group['id']


def test_deleted_cancelled_and_draft_are_not_actionable(owner,opened):
    poll,_=opened
    data(owner.post(path(poll)+'/cancel',json={}))
    assert dashboard(owner)['pending_polls']['total']==0
    data(owner.post(path(poll)+'/delete',json={}))
    assert dashboard(owner)['pending_polls']['total']==0
    data(owner.post(path(poll)+'/restore',json={}))
    assert dashboard(owner)['pending_polls']['total']==0


def test_ongoing_and_archived_meetings_still_visible_tasks_independent(owner,other,meeting):
    row,now=meeting
    task=data(create_task(owner,row,body(now)),201)
    value=dashboard(other)
    assert value['upcoming_meetings']['total']==1 and value['tasks']['items'][0]['id']==task['id']
    assert value['tasks']['items'][0]['version']==1
    data(owner.post(f"/api/v1/polls/{row['poll_id']}/archive",json={}))
    assert dashboard(other)['tasks']['total']==1
    assert dashboard(other)['upcoming_meetings']['total']==1
    now[0]=NOW+120001
    assert dashboard(other)['upcoming_meetings']['total']==1
    now[0]=NOW+180000
    assert dashboard(other)['upcoming_meetings']['total']==0
    assert dashboard(other)['tasks']['total']==1 # overdue is not completed


@pytest.mark.parametrize('status',['DONE','CANCELLED'])
def test_completed_and_cancelled_tasks_not_counted(owner,other,meeting,status):
    row,now=meeting;task=data(create_task(owner,row,body(now)),201)
    data(owner.patch(f"/api/v1/tasks/{task['id']}/status",json={'status':status,'expected_version':1}))
    assert dashboard(other)['tasks']=={'total':0,'items':[]}
    assert dashboard(owner)['tasks']['total']==0


def test_totals_and_five_item_cap_with_stable_deadline_order(owner,setup):
    group,_=setup
    values=[]
    for index in range(7):
        from app.common.times import format_ms
        poll=data(create_poll(owner,group,draft(title=f'排期{index}',response_deadline=format_ms(NOW+60000+index*1000))),201)
        data(owner.post(path(poll)+'/open',json={}))
        values.append(poll)
    value=dashboard(owner)['pending_polls']
    assert value['total']==7
    assert [p['id'] for p in value['items']]==[p['id'] for p in values[:5]]
