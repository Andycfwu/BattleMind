"""Offline orchestration/audit regressions; no battle collection."""
import json
import time
from types import SimpleNamespace

import pytest

from diagnostics import acceptance_live_verify as live
from battlemind.acceptance import ChainWriter


def test_live_inspection_reads_each_sealed_own_journal(tmp_path,monkeypatch):
    private=tmp_path/'recording';private.mkdir();(tmp_path/'privileged/attempts').mkdir(parents=True)
    session='1'*32;build='2'*64
    (private/'session.json').write_text(json.dumps({'session':session,'build':build}))
    row={'decision_id':'fixture'}
    for side in ('a','b'):
        chain=ChainWriter(private/f'000-{side}.client.jsonl',session=session,build=build,channel='client',room='battle-gen1ou-fixture')
        chain.event('attempt',decision=row);chain.close()
        (tmp_path/f'privileged/attempts/000-{side}.jsonl').write_text(json.dumps(row)+'\n')
    (tmp_path/'events.jsonl').write_text('')
    monkeypatch.setattr(live,'replay_match',lambda *a:{'decisions':2})
    # Acceptance semantics have separate source-grounded trace tests. Here the
    # valid-result branch must read actual sealed chains and compare own journals.
    monkeypatch.setattr(live,'validate_acceptance',lambda *a,**k:{'integrity':'valid','attempts':[{'status':'committed'}]*2})
    battle={'match':0,'status':'completed','invalid_actions':0,'battle_tags':['battle-gen1ou-fixture'],
            'engine_record':{'path':'unused.json','sha256':'fixture'}}
    assert live.inspect_match(tmp_path,battle,None,None,private)['blocking_errors']==[]


def test_single_24_game_budget_reserves_cleanup_and_never_retries(tmp_path):
    from diagnostics.acceptance_instrumented_only import Budget
    now=[0.];b=Budget.create(tmp_path,clock=lambda:now[0])
    with pytest.raises(ValueError,match='Preflight'):b.begin('instrumented')
    now[0]=3;b.finish('preflight',True);b.begin('instrumented')
    assert b.deadline('instrumented')<=340
    for i in range(24):b.request('instrumented',i);now[0]+=1
    with pytest.raises(ValueError):b.request('instrumented',24)
    b.finish('instrumented',True);b.stop_collection();b.begin('reporting')
    assert b.deadline('reporting')<=400
    b.finish('reporting',True);b.close()
    before=b.path.read_bytes();now[0]+=500;b.close('late report');b.finish('instrumented',False)
    assert b.path.read_bytes()==before and b.data['state']=='finished'
    assert b.data['phases']['instrumented']['requested_indices']==list(range(24))


def test_reservation_guard_does_not_spend_unavailable_game(tmp_path):
    from diagnostics.acceptance_instrumented_only import Budget
    now=[0.];b=Budget.create(tmp_path,clock=lambda:now[0]);b.finish('preflight',True);b.begin('instrumented')
    now[0]=175
    with pytest.raises(ValueError,match='guard'):b.request('instrumented',0)
    assert b.stage('instrumented')['requested']==0


def test_failed_preflight_only_runs_mandatory_report(tmp_path,monkeypatch):
    from diagnostics import acceptance_instrumented_only as single
    root=tmp_path/'new';monkeypatch.setattr(single,'OUTPUT',root);calls=[]
    def run(root,name,budget):
        calls.append(name)
        if name=='preflight':raise ValueError('fixture operational failure')
        single.reporting(root,single.DeadlineIO(budget.deadline(name)))
    monkeypatch.setattr(single,'run_worker',run)
    assert not single.main(root) and calls==['preflight','reporting']
    report=json.loads((root/'report.json').read_text())
    assert report['counts']['requested']==report['counts']['completed']==0
    assert report['counts']['never_requested']==24
    before=(root/'ledger.json').read_bytes()
    with pytest.raises(FileExistsError):single.main(root)
    assert (root/'ledger.json').read_bytes()==before


def test_report_failure_cannot_restart_collection_and_outcomes_unavailable(tmp_path,monkeypatch):
    from diagnostics import acceptance_instrumented_only as single
    root=tmp_path/'new';monkeypatch.setattr(single,'OUTPUT',root);calls=[]
    def run(root,name,budget):
        calls.append(name)
        if name=='instrumented':budget.request(name,0);raise ValueError('fixture crash')
        if name=='reporting':raise TimeoutError('blocked reporting worker')
    monkeypatch.setattr(single,'run_worker',run)
    assert not single.main(root) and calls==['preflight','instrumented','reporting']
    result=json.loads((root/'report.json').read_text())
    assert result['requested']==1 and result['completed'] is None and result['never_requested']==23
    budget=single.Budget(root)
    with pytest.raises(ValueError):budget.begin('instrumented')


def test_frozen_spec_matches_retained_science_and_only_one_phase():
    from diagnostics import acceptance_instrumented_only as single
    spec=json.loads(single.SPEC.read_text());single.validate_spec(spec)
    assert spec['maximum_games']==24 and spec['phase_seconds']==single.ALLOCATIONS
    for key,value in [('maximum_games',25),('policy_seed',7),('host','0.0.0.0'),('retries',True)]:
        changed={**spec,key:value}
        with pytest.raises(ValueError):single.validate_spec(changed)


def test_reporting_of_an_ordinary_cap_is_not_a_win(tmp_path,monkeypatch):
    from diagnostics import acceptance_instrumented_only as single
    b=single.Budget.create(tmp_path);b.finish('preflight',True);b.begin('instrumented');b.request('instrumented',0)
    (tmp_path/'instrumented').mkdir();row={'match':0,'status':'truncated','winner':'a','invalid_actions':0}
    (tmp_path/'instrumented/battles.jsonl').write_text(json.dumps(row)+'\n')
    b.finish('instrumented',False,'fixture cap');b.stop_collection('fixture cap');b.begin('reporting')
    monkeypatch.setattr(single,'audit_run',lambda *a:{'functional_recording_passed':False,'coverage':{'unobserved':['clamp_continuation']},'isolation':{'status':'unavailable'},'known_warnings':0,'unexpected_warnings':0})
    single.reporting(tmp_path,single.DeadlineIO(b.deadline('reporting')))
    report=json.loads((tmp_path/'report.json').read_text())
    assert report['counts']['truncated']==1 and report['counts']['a_wins']==report['counts']['completed']==0
    assert not report['functional_recording_passed']
