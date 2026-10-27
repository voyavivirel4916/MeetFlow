"""T22 independent samples, exhaustive small states and deterministic shuffles."""
from dataclasses import asdict
from itertools import product
from pathlib import Path
from random import Random
import re

import pytest

from app.recommendations.core import Answer, Candidate, Person, rank_slots


def document_sample():
    text = (Path(__file__).resolve().parents[3] / 'Docs/09-需求分析文档.md').read_text(encoding='utf-8-sig')
    rows = [[cell.strip() for cell in line.strip('|').split('|')] for line in text.splitlines() if re.match(r'^\| T[123] \|', line)]
    assert len(rows) == 3
    people = [Person(1,'REQUIRED'),Person(2,'REQUIRED'),Person(3,'NORMAL'),Person(4,'NORMAL')]
    slots = [Candidate(i, i*3600_000, (i+1)*3600_000) for i in range(1,4)]
    states = {'有空':'AVAILABLE','勉强':'MAYBE','没空':'UNAVAILABLE','未填':None}
    answers = [Answer(user, slot, states[value]) for slot,row in enumerate(rows,1) for user,value in enumerate(row[1:5],1)]
    return rows, people, slots, answers


def test_authority_markdown_samples_are_executed_by_the_actual_engine():
    rows,people,slots,answers = document_sample()
    by_id = {item.slot_id:item for item in rank_slots(people,slots,answers)}
    for identifier,row in enumerate(rows,1):
        item = by_id[identifier]
        assert (item.base_score,item.required_unavailable_count,item.unsubmitted_count,item.score,item.rank) == tuple(map(int,[row[5],row[6],row[7],row[8],row[9]]))


def test_all_256_four_person_states_match_an_independent_oracle():
    people = [Person(1,'REQUIRED'),Person(2,'REQUIRED'),Person(3,'NORMAL'),Person(4,'NORMAL')]
    for states in product(['AVAILABLE','MAYBE','UNAVAILABLE',None],repeat=4):
        item = rank_slots(people,[Candidate(1,0,100)],[Answer(i,1,value) for i,value in enumerate(states,1)])[0]
        contributions = [(3 if i<2 else 1)*(2 if value=='AVAILABLE' else 1 if value=='MAYBE' else -2 if value=='UNAVAILABLE' else 0) for i,value in enumerate(states)]
        unknown = states.count(None)
        required_no = states[:2].count('UNAVAILABLE')
        assert item.base_score == sum(contributions)
        assert item.score == sum(contributions)-20*required_no-2*unknown
        assert (item.available_count,item.maybe_count,item.unavailable_count,item.unsubmitted_count) == tuple(states.count(value) for value in ['AVAILABLE','MAYBE','UNAVAILABLE',None])
        assert item.required_unsubmitted_count == states[:2].count(None)
        assert item.required_maybe_count == states[:2].count('MAYBE')
        assert item.conflict_user_ids == tuple(i for i,value in enumerate(states,1) if value=='UNAVAILABLE')
        if any(value != 'AVAILABLE' for value in states[:2]):
            assert '必到成员均已填写有空' not in item.reason


def test_one_hundred_seeded_input_permutations_keep_all_explanations_and_ids_stable():
    _rows,people,slots,answers = document_sample()
    expected = rank_slots(people,slots,answers)
    generator = Random(20261027)
    for _ in range(100):
        shuffled = [list(people),list(slots),list(answers)]
        for items in shuffled:
            generator.shuffle(items)
        assert rank_slots(*shuffled) == expected


@pytest.mark.parametrize('state,score',[('AVAILABLE',80),('MAYBE',40),('UNAVAILABLE',-280),(None,-40)])
def test_twenty_by_fifteen_extremes(state,score):
    people = [Person(i,'REQUIRED' if i<=10 else 'NORMAL') for i in range(1,21)]
    slots = [Candidate(i,i*100,(i+1)*100) for i in range(1,16)]
    answers = [Answer(person.user_id,slot.id,state) for slot in slots for person in people]
    result = rank_slots(people,slots,answers)
    assert len(result) == 15
    assert [item.rank for item in result] == list(range(1,16))
    assert all(item.score == score for item in result)
    assert all(item.available_count+item.maybe_count+item.unavailable_count+item.unsubmitted_count == 20 for item in result)
    if state == 'UNAVAILABLE':
        assert all('所有候选时段均有成员没空' in item.reason for item in result)
    if state is None:
        assert all(item.required_unsubmitted_count == 10 and '出席情况尚未确定' in item.reason for item in result)


def test_all_conflicting_candidates_are_ranked_without_a_false_no_conflict_claim():
    people = [Person(1,'REQUIRED'),Person(2,'NORMAL')]
    slots = [Candidate(1,0,100),Candidate(2,100,200)]
    answers = [Answer(1,1,'UNAVAILABLE'),Answer(2,1,'AVAILABLE'),Answer(1,2,'AVAILABLE'),Answer(2,2,'UNAVAILABLE')]
    result = rank_slots(people,slots,answers)
    assert [item.slot_id for item in result] == [2,1]
    assert all('排名不代表全员可参加' in item.reason for item in result)
    assert all('无冲突最佳' not in item.reason for item in result)


def test_final_keys_handle_identical_start_and_end_independent_of_input_order():
    people = [Person(1,'NORMAL')]
    slots = [Candidate(99,10,30),Candidate(8,10,20),Candidate(7,0,20),Candidate(6,10,20)]
    for order in [slots,list(reversed(slots))]:
        assert [item.slot_id for item in rank_slots(people,order,[])] == [7,6,8,99]


def test_reason_is_derived_only_from_inputs_and_does_not_contain_mutable_ranking_state():
    _rows,people,slots,answers = document_sample()
    first = rank_slots(people,slots,answers)
    altered = [Answer(answer.user_id,answer.slot_id,'AVAILABLE') for answer in answers]
    second = rank_slots(people,slots,altered)
    assert [asdict(item) for item in first] != [asdict(item) for item in second]
    assert rank_slots(people,slots,answers) == first


@pytest.mark.parametrize('people,slots,answers',[
    ([Person(i,'NORMAL') for i in range(1,22)],[Candidate(1,0,1)],[]),
    ([Person(1,'NORMAL')],[Candidate(i,i,i+1) for i in range(1,17)],[]),
    ([Person(1,'NORMAL')],[Candidate(1,0.5,1)],[]),
    ([Person(1,'NORMAL')],[Candidate(1,True,100)],[]),
    ([Person(1,[])],[Candidate(1,0,100)],[]),
    ([Person(1,'NORMAL')],[Candidate(1,0,100)],[Answer(1,1,[])]),
])
def test_boundary_invalid_inputs_fail_before_scoring(people,slots,answers):
    with pytest.raises(ValueError):
        rank_slots(people,slots,answers)
