"""Offline fixtures test mechanics; none are acceptance battle evidence."""
from collections import Counter
from dataclasses import FrozenInstanceError, replace
import json

import numpy as np
import pytest

from battlemind.actor_step import controlled_update
from battlemind.actor_step_experiment import (CONFIG, ARMS, FINAL_ARMS, BLOCKING,
    candidate_path, choose_checkpoints, schedule, validate_spec, report_experiment)
from battlemind.actor_step_report import build_report, draw_index
from battlemind.adapter import snapshot_request
from battlemind.environment import ROOT, sha256
from battlemind.reinforce import Checkpoint, Parameters, distribution, load_checkpoint, save_checkpoint
from battlemind.reinforce_experiment import Ledger, verify_opponents
from battlemind.reinforce_training import Episode, Step, update, trajectories


@pytest.fixture
def obs(turn_request,tracker):return snapshot_request(turn_request,1,tracker)[0]


def episodes(obs, params):
    p,v,logits,s,a=distribution(obs,params)
    return [Episode(f'toy:{i}','0'*64,r,tuple(Step(s,a,logits,j%len(p),p,v) for j in range(i+1)),'training')
            for i,r in enumerate((1.,-1.,0.))]


@pytest.mark.parametrize('nonzero',[False,True])
def test_control_exactly_reproduces_original_parameters_and_metrics(obs,nonzero):
    params=Parameters.initial()
    if nonzero:
        w=np.zeros_like(params.actor);w[3,8]=.13
        v=np.zeros_like(params.value);v[0]=-.04
        params=Parameters(tuple(map(tuple,w)),tuple(v))
    cp=Checkpoint(params,'0'*64);data=episodes(obs,params)
    original,old_metrics=update(cp,data,30,.1)
    control,new_metrics=controlled_update(cp,data,1)
    assert control==original
    assert all(new_metrics[k]==v for k,v in old_metrics.items())


def test_treatment_multiplies_only_actor_step_after_same_normalization(obs):
    cp=Checkpoint(Parameters.initial(),'0'*64);data=episodes(obs,cp.parameters)
    before=repr(cp)
    control,c=controlled_update(cp,data,1);treatment,t=controlled_update(cp,data,10)
    assert control.value==treatment.value and c['value_delta_l2']==t['value_delta_l2']
    assert c['actor_gradient_norm']==t['actor_gradient_norm']
    assert c['value_gradient_norm']==t['value_gradient_norm']
    assert np.array_equal(np.asarray(control.actor)*10,np.asarray(treatment.actor)) or np.allclose(np.asarray(control.actor)*10,treatment.actor,atol=1e-16)
    assert t['actor_delta_l2']==pytest.approx(10*c['actor_delta_l2'])
    assert t['applied_vs_same_input_control_delta_ratio']==pytest.approx(10)
    assert not t['actor_projected'] and not t['actor_gradient_clipped']
    assert before==repr(cp)
    with pytest.raises(FrozenInstanceError):treatment.value=(1,)


@pytest.mark.parametrize('gradient',[.001,2.0])
def test_clip_then_multiplier_then_projection(monkeypatch,gradient):
    import battlemind.actor_step as module
    cp=Checkpoint(Parameters.initial(),'0'*64)
    ga=np.zeros_like(cp.parameters.actor);ga[0,0]=gradient
    gv=np.zeros_like(cp.parameters.value);gv[0]=.03
    step=Step(np.zeros(37),np.zeros((1,22)),np.zeros(1),0,np.ones(1),0.)
    ep=Episode('x:0','0'*64,1.,(step,),'training')
    monkeypatch.setattr(module,'gradients',lambda *args:(ga,gv,{'mean_reward':1.}))
    control,c=controlled_update(cp,[ep],1);treatment,t=controlled_update(cp,[ep],10)
    assert control.value==treatment.value
    assert t['actor_preprojection_step_l2']==pytest.approx(c['actor_preprojection_step_l2']*10)
    assert t['actor_gradient_clipped']==(gradient>1)
    assert t['actor_delta_l2']==pytest.approx(min(6,300*min(gradient,1)))
    if gradient>1:
        assert t['actor_delta_l2']==c['actor_delta_l2']==6
        assert t['applied_vs_same_input_control_delta_ratio']==1


@pytest.mark.parametrize('gain',[0,2,100,True,1.0,float('nan'),float('inf'),'10'])
def test_reject_unreviewed_or_malformed_gains(obs,gain):
    cp=Checkpoint(Parameters.initial(),'0'*64)
    with pytest.raises(ValueError):controlled_update(cp,episodes(obs,cp.parameters),gain)


@pytest.mark.parametrize('bad',['value','probability','state','phase','hash','reward'])
def test_corrupt_or_incompatible_trajectories_stop(obs,bad):
    cp=Checkpoint(Parameters.initial(),'0'*64);ep=episodes(obs,cp.parameters)[0];step=ep.steps[0]
    if bad=='value':ep=replace(ep,steps=(replace(step,value=float('nan')),))
    if bad=='probability':ep=replace(ep,steps=(replace(step,probabilities=np.full_like(step.probabilities,np.nan)),))
    if bad=='state':ep=replace(ep,steps=(replace(step,state=np.full_like(step.state,np.nan)),))
    if bad=='phase':ep=replace(ep,phase='final')
    if bad=='hash':ep=replace(ep,checkpoint_sha256='1'*64)
    if bad=='reward':ep=replace(ep,reward=None)
    with pytest.raises(ValueError):controlled_update(cp,[ep],10)


def test_exact_balanced_schedule_and_equal_non_gain_settings():
    config=json.loads(CONFIG.read_text());validate_spec(config);plan=schedule(config)
    assert Counter(e['phase'] for e in plan)=={'training':36,'selection':15,'final':36}
    assert sum(24 for _ in plan)==2088
    assert len({(e['phase'],e['name']) for e in plan})==87
    assert config['arms']=={'control':1,'treatment':10}
    for batch in range(1,7):
        arms=[]
        for arm in ARMS:
            rows=[e for e in plan if e['phase']=='training' and e['batch']==batch and e['arm']==arm]
            arms.append([(r['opponent'].replace(arm,'own'),r['seed']) for r in rows])
        assert arms[0]==arms[1]
    for arm in FINAL_ARMS:
        entries=[e for e in plan if e['phase']=='final' and e['arm']==arm]
        assert len(entries)==12
        assert Counter(e['opponent'] for e in entries)==dict.fromkeys(config['final_panel'],2)
    changed={**config,'value_lr':1.}
    with pytest.raises(ValueError):validate_spec(changed)


def test_frozen_pool_validation_detects_checkpoint_changes(tmp_path):
    path=tmp_path/'model.json';save_checkpoint(path,Parameters.initial(),{})
    pool=({'identity':'opaque','checkpoint':str(path),'sha256':sha256(path)},)
    verify_opponents(pool)
    path.write_text('{}')
    with pytest.raises(ValueError,match='changed'):verify_opponents(pool)


def test_selection_shared_initialization_and_deterministic_tie(tmp_path):
    save_checkpoint(candidate_path(tmp_path,'initial'),Parameters.initial(),{})
    for arm in ARMS:
        for number in (3,6):save_checkpoint(candidate_path(tmp_path,f'{arm}-c{number}'),Parameters.initial(),{})
    records=[]
    for entry in schedule(json.loads(CONFIG.read_text())):
        if entry['phase']!='selection':continue
        path=tmp_path/'selection'/entry['name'];path.mkdir(parents=True)
        # Equal complete terminal results: earliest c0 wins every tie.
        (path/'battles.jsonl').write_text('\n'.join(json.dumps({'match':i,'status':'completed','winner':'draw'}) for i in range(24)))
        records.append({**entry,'path':path.relative_to(tmp_path).as_posix(),'status':'recorded'})
    chosen=choose_checkpoints(tmp_path,records)
    assert all(row['identity']=='initial' for row in chosen['choices'].values())
    with pytest.raises(ValueError,match='Incomplete'):choose_checkpoints(tmp_path,records[:-1])


def test_budget_protects_future_phases_partial_requests_and_idempotence(tmp_path):
    config=json.loads(CONFIG.read_text());clock=[0.]
    ledger=Ledger(tmp_path,config,clock=lambda:clock[0]);ledger.begin('training')
    index=ledger.reserve({'path':'synthetic'})
    assert ledger.data['phases']['final']['state']=='reserved'
    assert ledger.data['phases']['selection']['state']=='reserved'
    assert ledger.data['phases']['training']['requested']==0
    ledger.dispatch(index)
    with pytest.raises(ValueError):ledger.dispatch(index)
    clock[0]=1111
    with pytest.raises(ValueError,match='exhausted'):ledger.reserve({})
    ledger.end(failed=True);ledger.finish('test stop');before=(tmp_path/'ledger.json').read_bytes()
    clock[0]=10000;ledger.end(failed=True);ledger.finish()
    assert before==(tmp_path/'ledger.json').read_bytes()
    assert ledger.data['phases']['final']['requested']==0
    assert ledger.data['phases']['training']['requested']==24


def test_untouched_final_reports_zero_requests_not_losses(tmp_path):
    config=json.loads(CONFIG.read_text());ledger=Ledger(tmp_path,config)
    ledger.data['arm_planned_games']={'training':dict.fromkeys(ARMS,432),
        'selection':dict.fromkeys(('initial','control-c3','control-c6','treatment-c3','treatment-c6'),72),
        'final':dict.fromkeys(FINAL_ARMS,288)}
    result=build_report(tmp_path,ledger.data,config)
    for arm in FINAL_ARMS:
        summary=result['by_arm']['final'][arm]['overall']
        assert summary['requested']==summary['unrecorded']==summary['b_wins']==0
        assert summary['never_requested']==288 and summary['completed_mean_terminal_reward'] is None
    assert not result['comparisons']['treatment-minus-control']['available']
    (tmp_path/'summary.json').write_text(json.dumps({'ledger':ledger.data,'report':result}))
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    assert report_experiment(tmp_path)==report_experiment(tmp_path)
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_cap_is_separate_and_not_a_blocking_error_or_reward():
    from battlemind.actor_step_report import aggregate
    assert 'truncated' not in BLOCKING
    r=aggregate([{'match':0,'status':'truncated','winner':None}],1)
    assert r['completed']==r['a_wins']==r['b_wins']==r['draws']==0
    assert r['completed_mean_terminal_reward'] is None and r['incomplete_requested']==1


def test_cdf_report_preserves_repaired_sampler_boundary():
    assert draw_index(np.array([.5,.5]),.5)==1
    assert draw_index(np.array([.5,.5]),0.)==0
    for bad in (None,True,'0.1',-1.,1.,float('nan')):
        with pytest.raises(ValueError):draw_index(np.array([.5,.5]),bad)


def test_retained_first_update_control_exactly_reconstructs_original():
    root=ROOT/'runs/reinforce-main'
    if not root.exists():pytest.skip('Retained inputs required; no regeneration')
    parent=load_checkpoint(root/'checkpoints/c0.json');data=[]
    for opponent in ('v2','v5','c0'):
        episodes_,_=trajectories(root/f'training/b1-vs-{opponent}',parent,'training');data+=episodes_
    result,metrics=controlled_update(parent,data,1)
    original=json.loads((root/'batches/update-1.json').read_text())['metrics']
    assert result==load_checkpoint(root/'checkpoints/c1.json').parameters
    assert all(metrics[k]==v for k,v in original.items())
