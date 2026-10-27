from copy import deepcopy
import sqlite3

import pytest

from app.db.connection import database_path, make_engine
from app.recommendations.core import Answer, Candidate, Person, rank_slots
from app.votes.models import VotesIn
from app.votes.service import save_votes
from test_bootstrap import assert_error
from test_groups import data, other, owner
from test_matrix import matrix_poll, submit
from test_polls import NOW, create_poll, draft, rows, setup
from test_votes import answers


def baseline():
    people = [Person(1,'REQUIRED'),Person(2,'REQUIRED'),Person(3,'NORMAL'),Person(4,'NORMAL')]
    slots = [Candidate(1,1000,2000),Candidate(2,2000,3000),Candidate(3,3000,4000)]
    values = [('AVAILABLE','AVAILABLE','UNAVAILABLE','UNAVAILABLE'),
              ('AVAILABLE','UNAVAILABLE','AVAILABLE','AVAILABLE'),('AVAILABLE',None,'AVAILABLE','MAYBE')]
    votes = [Answer(user+1,slot+1,value) for slot,row in enumerate(values) for user,value in enumerate(row)]
    return people,slots,votes


def test_baseline_scores_counts_conflicts_and_explanation():
    result = rank_slots(*baseline())
    assert [item.slot_id for item in result] == [1,3,2]
    assert [item.rank for item in result] == [1,2,3]
    assert [item.base_score for item in result] == [8,9,4]
    assert [item.score for item in result] == [8,7,-16]
    assert [item.conflict_user_ids for item in result] == [(3,4),(),(2,)]
    assert result[1].required_unsubmitted_count == 1
    assert '出席情况尚未确定' in result[1].reason
    assert '必到成员均已填写有空' not in result[1].reason
    assert '基础分9' in result[1].reason and '未填扣分2' in result[1].reason
    for item in result:
        assert item.available_count+item.maybe_count+item.unavailable_count+item.unsubmitted_count == 4
        assert item.score == item.base_score-20*item.required_unavailable_count-2*item.unsubmitted_count


def test_same_input_reordered_is_deterministic_and_not_modified():
    inputs = baseline()
    before = deepcopy(inputs)
    expected = rank_slots(*inputs)
    assert rank_slots(*[list(reversed(items)) for items in inputs]) == expected
    assert inputs == before


def test_required_conflict_precedes_a_higher_score():
    people = [Person(1,'REQUIRED')]+[Person(i,'NORMAL') for i in range(2,21)]
    slots = [Candidate(1,100,200),Candidate(2,200,300)]
    votes = [Answer(person.user_id,slot.id,
        ('AVAILABLE' if person.user_id == 1 else 'UNAVAILABLE') if slot.id == 1 else
        ('UNAVAILABLE' if person.user_id == 1 else 'AVAILABLE')) for person in people for slot in slots]
    result = rank_slots(people,slots,votes)
    assert [item.slot_id for item in result] == [1,2]
    assert result[0].score < result[1].score


def test_score_then_available_count_break_ties():
    people = [Person(i,'NORMAL') for i in range(1,5)]
    slots = [Candidate(1,300,400),Candidate(2,200,300),Candidate(3,100,200)]
    votes = [Answer(person.user_id,slot.id,'AVAILABLE' if slot.id == 3 or (slot.id == 1 and person.user_id < 4)
                    else 'UNAVAILABLE' if slot.id == 1 else 'MAYBE') for person in people for slot in slots]
    result = rank_slots(people,slots,votes)
    assert [item.slot_id for item in result] == [3,1,2]
    assert result[1].score == result[2].score == 4
    assert result[1].available_count == 3 and result[2].available_count == 0


def test_start_end_and_id_are_final_stable_keys():
    slots = [Candidate(9,100,300),Candidate(8,100,200),Candidate(7,0,200),Candidate(6,100,200)]
    assert [item.slot_id for item in rank_slots([Person(1,'REQUIRED')],slots,[])] == [7,6,8,9]


@pytest.mark.parametrize('value,score,warning',[('AVAILABLE',6,'所有参与者均已填写有空'),('MAYBE',3,'需要协调'),
    ('UNAVAILABLE',-26,'所有候选时段均有成员没空'),(None,-2,'出席情况尚未确定')])
def test_single_required_member_risks(value,score,warning):
    item = rank_slots([Person(1,'REQUIRED')],[Candidate(1,0,100)],[Answer(1,1,value)])[0]
    assert item.score == score and warning in item.reason
    assert item.required_maybe_count == (value == 'MAYBE')
    assert item.required_unavailable_count == (value == 'UNAVAILABLE')
    if value != 'AVAILABLE':
        assert '所有参与者均已填写有空' not in item.reason


def test_sparse_unknown_and_explicit_null_match_without_required_members():
    people, slots = [Person(1,'NORMAL')],[Candidate(1,0,100)]
    assert rank_slots(people,slots,[]) == rank_slots(people,slots,[Answer(1,1,None)])
    assert '未设置必到成员' in rank_slots(people,slots,[])[0].reason


@pytest.mark.parametrize('people,slots,votes',[
    ([],[Candidate(1,0,100)],[]),([Person(1,'NORMAL')],[],[]),
    ([Person(1,'NORMAL')]*2,[Candidate(1,0,100)],[]),
    ([Person(True,'NORMAL')],[Candidate(1,0,100)],[]),
    ([Person(1,'OWNER')],[Candidate(1,0,100)],[]),
    ([Person(1,'NORMAL')],[Candidate(1,100,100)],[]),
    ([Person(1,'NORMAL')],[Candidate(1,0,100)]*2,[]),
    ([Person(1,'NORMAL')],[Candidate(1,0,100)],[Answer(2,1,'AVAILABLE')]),
    ([Person(1,'NORMAL')],[Candidate(1,0,100)],[Answer(1,2,'AVAILABLE')]),
    ([Person(1,'NORMAL')],[Candidate(1,0,100)],[Answer(1,1,'AVAILABLE')]*2),
    ([Person(1,'NORMAL')],[Candidate(1,0,100)],[Answer(1,1,'UNKNOWN')]),
])
def test_invalid_pure_inputs_are_rejected(people,slots,votes):
    with pytest.raises(ValueError):
        rank_slots(people,slots,votes)


def path(poll):
    return f"/api/v1/polls/{poll['id']}/recommendations"


def test_api_recomputes_scores_from_current_saved_answers(owner,other,matrix_poll,settings):
    poll, _ = matrix_poll
    # Fully submitted variant of the document sample; slot 3 now has both required members available.
    submit(owner,poll,['AVAILABLE']*3)
    submit(other,poll,['AVAILABLE','UNAVAILABLE','AVAILABLE'])
    engine = make_engine(database_path(settings))
    try:
        save_votes(engine,3,poll['id'],VotesIn.model_validate(answers(poll,['UNAVAILABLE','AVAILABLE','AVAILABLE'])))
        save_votes(engine,4,poll['id'],VotesIn.model_validate(answers(poll,['UNAVAILABLE','AVAILABLE','MAYBE'])))
    finally:
        engine.dispose()
    response = data(owner.get(path(poll)))
    assert response['poll_id'] == poll['id']
    assert [item['slot_id'] for item in response['items']] == [poll['slots'][i]['id'] for i in [2,0,1]]
    assert [item['score'] for item in response['items']] == [15,8,-16]
    for item in response['items']:
        assert item['available_count']+item['maybe_count']+item['unavailable_count']+item['unsubmitted_count'] == 4
    submit(other,poll,['UNAVAILABLE']*3)
    updated = data(owner.get(path(poll)))
    assert updated != response
    assert all(item['required_unavailable_count'] == 1 for item in updated['items'])
    assert data(owner.get(path(poll)+'?score=999999&rank=1')) == updated


@pytest.mark.parametrize('status',['OPEN','CLOSED','CONFIRMED'])
def test_readable_states_do_not_write_or_store_results(owner,matrix_poll,settings,status):
    poll, _ = matrix_poll
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE polls SET status=? WHERE id=?',(status,poll['id']))
    before = rows(settings)
    result = data(owner.get(path(poll)))
    assert len(result['items']) == 3
    assert all(item['required_unsubmitted_count'] == 2 for item in result['items'])
    assert rows(settings) == before


@pytest.mark.parametrize('status',['DRAFT','CANCELLED'])
def test_draft_and_cancelled_reject_recommendations(owner,matrix_poll,settings,status):
    poll, _ = matrix_poll
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE polls SET status=? WHERE id=?',(status,poll['id']))
    before = rows(settings)
    assert_error(owner.get(path(poll)),409,'STATE_CONFLICT')
    assert rows(settings) == before


def test_member_not_in_roster_can_read_outsider_and_anonymous_cannot(owner,other,setup,settings):
    group, _ = setup
    poll = data(create_poll(owner,group,draft(participants=[{'user_id':1,'importance':'REQUIRED'}])),201)
    data(owner.post(f"/api/v1/polls/{poll['id']}/open",json={}))
    assert len(data(other.get(path(poll)))['items']) == 1
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('DELETE FROM group_members WHERE user_id=2 AND group_id=?',(group['id'],))
    assert_error(other.get(path(poll)),404,'NOT_FOUND')
    assert_error(other.get('/api/v1/polls/99999/recommendations'),404,'NOT_FOUND')
    other.cookies.clear()
    assert_error(other.get(path(poll)),401,'UNAUTHENTICATED')


def test_recommendation_counts_match_matrix_snapshot(owner,other,matrix_poll):
    poll, _ = matrix_poll
    submit(owner,poll)
    submit(other,poll,['MAYBE'])
    matrix = data(owner.get(f"/api/v1/polls/{poll['id']}/matrix"))
    result = data(owner.get(path(poll)))
    columns = {slot['id']:slot for slot in matrix['slots']}
    for item in result['items']:
        source = columns[item['slot_id']]
        assert [item[key] for key in ['available_count','maybe_count','unavailable_count','unsubmitted_count']] == [source[key] for key in ['available_count','maybe_count','unavailable_count','unanswered_count']]


def test_expired_open_can_read_without_materializing_close(owner,matrix_poll,settings):
    poll, now = matrix_poll
    now[0] = NOW+60_000
    before = rows(settings)
    assert len(data(owner.get(path(poll)))['items']) == 3
    assert rows(settings) == before
