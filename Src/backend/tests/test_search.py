import pytest
from test_bootstrap import assert_error
from test_groups import owner,other,create,data
from test_polls import setup,create_poll,draft
from test_votes import opened
from test_meetings import closed
from test_meeting_content import meeting
from test_tasks import body,create_task


def test_poll_search_filters_before_pagination_and_clears(owner,setup):
    group,_=setup
    ids=[]
    for i in range(5):
        poll=data(create_poll(owner,group,draft(title=f'接口评审 {i}')),201);ids.append(poll['id'])
    data(create_poll(owner,group,draft(title='其他安排')),201)
    url=f"/api/v1/groups/{group['id']}/polls"
    found=data(owner.get(url,params={'q':'  接口评审  ','page_size':2,'page':2}))
    assert found['total']==5 and [p['id'] for p in found['items']]==list(reversed(ids))[2:4]
    assert data(owner.get(url,params={'q':'   '}))['total']==6
    assert data(owner.get(url,params={'q':'不存在'}))=={'items':[],'page':1,'page_size':20,'total':0}


@pytest.mark.parametrize('query',['%','_','/','\\',"' OR 1=1 --",'设计 测试'])
def test_search_metacharacters_are_literal(owner,setup,query):
    group,_=setup
    expected=data(create_poll(owner,group,draft(title='包含'+query+'的排期')),201)
    data(create_poll(owner,group,draft(title='普通排期')),201)
    values=data(owner.get(f"/api/v1/groups/{group['id']}/polls",params={'q':query}))
    assert values['total']==1 and values['items'][0]['id']==expected['id']


def test_poll_search_preserves_visibility_and_permissions(owner,other,setup):
    group,_=setup
    poll=data(create_poll(owner,group,draft(title='旧计划')),201)
    data(owner.post(f"/api/v1/polls/{poll['id']}/delete",json={}))
    url=f"/api/v1/groups/{group['id']}/polls"
    assert data(owner.get(url,params={'q':'旧计划'}))['total']==0
    assert data(owner.get(url,params={'q':'旧计划','view':'trash'}))['total']==1
    assert_error(other.get(url,params={'q':'旧计划','view':'trash'}),403,'FORBIDDEN')
    private=data(create(other),201)
    assert_error(owner.get(f"/api/v1/groups/{private['id']}/polls",params={'q':'旧计划'}),404,'NOT_FOUND')


def test_task_search_combines_status_assignee_and_meeting(owner,other,meeting):
    row,now=meeting
    first=data(create_task(owner,row,body(now,title='接口核对')),201)
    data(create_task(owner,row,body(now,title='接口说明',assignee_id=1)),201)
    data(create_task(owner,row,body(now,title='汇报准备')),201)
    assert data(other.get('/api/v1/tasks/mine',params={'q':'接口'}))['total']==1
    group_url=f"/api/v1/groups/{row['group_id']}/tasks"
    assert data(other.get(group_url,params={'q':'接口','meeting_id':row['id']}))['total']==2
    data(other.patch(f"/api/v1/tasks/{first['id']}/status",json={'status':'DONE','expected_version':1}))
    assert data(other.get('/api/v1/tasks/mine',params={'q':'接口'}))['total']==0
    assert data(other.get('/api/v1/tasks/mine',params={'q':'接口','status':'DONE'}))['total']==1
    assert data(other.get('/api/v1/tasks/mine',params={'q':''}))['total']==1


@pytest.mark.parametrize('query',['x'*101,'\x00'])
def test_invalid_search_is_rejected(owner,meeting,query):
    row,_=meeting
    for url in [f"/api/v1/groups/{row['group_id']}/polls",f"/api/v1/groups/{row['group_id']}/tasks",'/api/v1/tasks/mine']:
        assert_error(owner.get(url,params={'q':query}),422,'VALIDATION_ERROR')
