"""Offline tests only. No LocalServer, battle collector, or training invocation."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from diagnostics.acceptance_live_verify import Budget, SPEC, recorded_factories, validate_spec
from battlemind import runner


@pytest.fixture
def budget(tmp_path):
    now=[100.]
    spec=json.loads(SPEC.read_text());validate_spec(spec)
    b=Budget.create(tmp_path,spec,10.,clock=lambda:now[0]);b.preflight_done(True)
    return b,now


def test_reserves_both_phases_and_stops_without_reusing_game(budget):
    b,now=budget
    assert all(p['reserved']==24 and p['requested']==0 for p in b.data['phases'].values())
    b.begin('original');b.request('original',0)
    with pytest.raises(ValueError):b.request('original',0)
    now[0]+=115
    with pytest.raises(ValueError,match='reservation guard'):b.request('original',1)
    assert b.data['phases']['original']['requested']==1
    assert b.data['phases']['instrumented']['requested']==0


def test_finish_and_stop_times_are_idempotent_and_unstarted_is_zero(budget):
    b,now=budget;b.begin('original');now[0]+=12;b.finish('original',False,'fixture')
    first=json.dumps(b.data['phases']['original'],sort_keys=True)
    now[0]+=20;b.finish('original',True)
    assert json.dumps(b.data['phases']['original'],sort_keys=True)==first
    with pytest.raises(ValueError):b.begin('instrumented')
    b.close('fixture');total=b.data['total_seconds'];now[0]+=30;b.close()
    assert b.data['total_seconds']==total
    assert b.data['phases']['instrumented']['state']=='reserved'


def test_full_two_phase_schedule_has_exactly_48_requests(budget):
    b,now=budget
    for phase in ('original','instrumented'):
        b.begin(phase)
        for i in range(24):b.request(phase,i);now[0]+=.5
        with pytest.raises(ValueError):b.request(phase,24)
        b.finish(phase,True)
    b.begin_reporting();b.finish_reporting(True);b.close()
    assert b.data['state']=='finished' and sum(p['requested'] for p in b.data['phases'].values())==48
    assert b.data['overhead_seconds']==10


@pytest.mark.parametrize('key,value',[('maximum_games',49),('concurrency',2),('policy_seed',42),('training_updates',True)])
def test_rejects_changed_scientific_or_budget_spec(key,value):
    spec=json.loads(SPEC.read_text());spec[key]=value
    with pytest.raises(ValueError):validate_spec(spec)


def test_opt_in_factories_restore_after_failure(tmp_path):
    old=runner.LocalPlayer,runner.close_players
    with pytest.raises(RuntimeError):
        with recorded_factories(tmp_path,'1'*32,'2'*64):
            assert (runner.LocalPlayer,runner.close_players)!=old
            raise RuntimeError('fixture failure')
    assert (runner.LocalPlayer,runner.close_players)==old


def test_refuses_consumed_or_overlapping_phase(budget):
    b,_=budget;b.begin('original')
    with pytest.raises(ValueError):b.begin('original')


def test_preflight_deadline_prevents_phase_start_and_requests(tmp_path):
    now=[0.]
    b=Budget.create(tmp_path,json.loads(SPEC.read_text()),clock=lambda:now[0])
    now[0]=101.  # Future replacement gives preflight 100s, not all overhead.
    with pytest.raises(ValueError):b.begin('original')
    assert all(p['requested']==0 and p['state']=='reserved' for p in b.data['phases'].values())


def test_stopped_budget_cannot_start_server_phase(budget):
    b,_=budget;b.close('preflight cancelled')
    with pytest.raises(ValueError):b.begin('original')
    assert sum(p['requested'] for p in b.data['phases'].values())==0


def test_reading_closed_durations_is_immutable_and_read_only(budget):
    b,now=budget;b.close('preflight expired')
    before=b.path.read_bytes();total=b.total();overhead=b.overhead()
    now[0]+=500
    assert b.total()==total and b.overhead()==overhead
    assert b.path.read_bytes()==before


def test_preflight_stop_records_actual_overrun_once(tmp_path):
    now=[0.];b=Budget.create(tmp_path,json.loads(SPEC.read_text()),clock=lambda:now[0])
    now[0]=105;b.preflight_done(True)
    stopped=dict(b.data['preflight']);assert stopped['state']=='stopped' and stopped['seconds']==105
    now[0]=180;b.preflight_done(False,'again')
    assert b.data['preflight']==stopped
    with pytest.raises(ValueError):b.begin('original')
    b.close('expired');assert b.total()==180


def test_reporting_and_cleanup_are_reserved_before_any_collection(budget):
    b,now=budget;b.begin('original')
    assert b.data['reporting']['maximum_seconds']==60 and b.data['cleanup_reserve_seconds']==20
    assert b.deadline('original')<=b.data['started_monotonic']+600-10-80
    now[0]+=1;b.finish('original',True)
    b.begin('instrumented');now[0]+=1;b.finish('instrumented',True)
    b.begin_reporting();now[0]+=61;b.finish_reporting(True)
    first=dict(b.data['reporting']);assert first['state']=='stopped' and first['seconds']==61
    now[0]+=10;b.finish_reporting(True);assert b.data['reporting']==first
    b.close();assert b.data['state']=='stopped'


def test_final_accounting_keeps_reporting_deadline_failure_visible(budget):
    from diagnostics.acceptance_live_verify import finalize
    b,now=budget
    for name in ('original','instrumented'):b.begin(name);b.finish(name,True)
    b.begin_reporting();now[0]+=61;b.finish_reporting(True)
    finalize(b.path.parent,b,None)
    assert b.data['state']=='stopped'
    assert json.loads((b.path.parent/'report.json').read_text())['failure']=='Required stage incomplete'
    with pytest.raises(ValueError):b.begin('instrumented')
    b.finish('original',False)
    with pytest.raises(ValueError):b.begin('original')
