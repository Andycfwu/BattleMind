from dataclasses import asdict, FrozenInstanceError, replace
import json

import numpy as np
import pytest

from battlemind.adapter import snapshot, snapshot_request
from battlemind.reinforce import (Parameters, Checkpoint, ReinforceAgent, features,
    distribution, save_checkpoint, load_checkpoint, SHAPE, softmax)
from battlemind.reinforce_training import Episode, Step, gradients, update
from battlemind.reinforce_experiment import Ledger, selection_score, bootstrap, validate_spec
from battlemind.schema import LegalAction


@pytest.fixture
def obs(turn_request,tracker):return snapshot_request(turn_request,1,tracker)[0]


def checkpoint():return Checkpoint(Parameters.initial(),'0'*64)


def episode(obs,reward=1,phase='training',key='run:0'):
    p,v,logits,s,a=distribution(obs,Parameters.initial())
    return Episode(key,'0'*64,reward,(Step(s,a,logits,0,p,v),),phase)


def test_observer_only_and_deep_freeze(battle,tracker,obs):
    obs,_=snapshot(battle,tracker)
    before=asdict(obs);state,action,_=features(obs)
    # Same request/public history with different wrapper hidden state and future result.
    battle._opponent_team={};battle._won=True
    second,_=snapshot(battle,tracker)
    assert np.array_equal(features(second)[0],state)
    assert np.array_equal(features(second)[1],action)
    with pytest.raises(FrozenInstanceError):obs.turn=99
    policy=ReinforceAgent(checkpoint(),42)
    policy.act(obs)
    assert asdict(obs)==before
    with pytest.raises(TypeError):policy.choose(battle)


def test_initialization_is_prior_softmax_not_v5_equivalence(obs):
    p,v,logits,*_=distribution(obs,Parameters.initial())
    assert v==0 and np.allclose(p,softmax(features(obs)[2]))
    assert p.shape==(len(obs.legal_actions),) and np.all(p>0) and np.isclose(p.sum(),1)


@pytest.mark.parametrize('kind',['ordinary','forced','engine'])
def test_variable_action_sets_have_only_legal_support(obs,kind):
    if kind=='forced':obs=replace(obs,request_kind='forced_switch',legal_actions=tuple(a for a in obs.legal_actions if a.kind=='switch'))
    if kind=='engine':obs=replace(obs,legal_actions=(LegalAction('engine:fight','engine','fight'),))
    agent=ReinforceAgent(checkpoint(),11)
    for _ in range(10):
        result=agent.act(obs)
        assert result.chosen_action in result.legal_ids==tuple(a.id for a in obs.legal_actions)
        assert len(result.probabilities)==len(obs.legal_actions)
    if len(obs.legal_actions)==1:
        assert result.probabilities==(1.0,)
        g,_,_=gradients(Parameters.initial(),[episode(obs)],'0'*64)
        assert np.count_nonzero(g)==0


def test_policy_randomness_reproducible_and_evaluation_immutable(obs):
    model=checkpoint();a,b=ReinforceAgent(model,17),ReinforceAgent(model,17)
    assert [a.act(obs) for _ in range(20)]==[b.act(obs) for _ in range(20)]
    assert model.parameters==Parameters.initial()


@pytest.mark.parametrize('invalid',[float('nan'),float('inf'),100.0])
def test_checkpoint_rejects_bad_parameters(tmp_path,invalid):
    path=tmp_path/'c.json';save_checkpoint(path,Parameters.initial(),{})
    data=json.loads(path.read_text());data['actor'][0][0]=invalid;path.write_text(json.dumps(data))
    with pytest.raises(ValueError):load_checkpoint(path)


def test_checkpoint_roundtrip_and_compatibility(tmp_path,obs):
    path=tmp_path/'model.json';old=save_checkpoint(path,Parameters.initial(),{'private_metadata':'never a feature'})
    current=load_checkpoint(path)
    assert old==current and ReinforceAgent(old,3).act(obs)==ReinforceAgent(current,3).act(obs)
    with pytest.raises(FileExistsError):save_checkpoint(path,Parameters.initial(),{})
    data=json.loads(path.read_text());data['compatibility']['snapshot']='future';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Incompatible'):load_checkpoint(path)


def test_analytic_actor_and_value_derivatives(obs):
    ep=episode(obs);step=ep.steps[0]
    ga,gv,_=gradients(Parameters.initial(),[ep],'0'*64)
    eps=1e-6
    for i,j in [(0,0),(0,1),(1,6),(4,7),(10,2)]:
        def loss(delta):
            w=np.zeros(SHAPE);w[i,j]=delta
            p=softmax(step.prior+step.actions@w.T@step.state)
            return -np.log(p[step.chosen])/100
        assert ga[i,j]==pytest.approx((loss(eps)-loss(-eps))/(2*eps),abs=1e-9)
    for i in (0,1,4,10):
        def vl(delta):return .5*(np.tanh(delta*step.state[i])-1)**2
        assert gv[i]==pytest.approx((vl(eps)-vl(-eps))/(2*eps),abs=1e-9)


def test_completed_outcomes_actually_change_parameters(obs):
    cp=checkpoint();p0=distribution(obs,cp.parameters)[0][0]
    won,metrics=update(cp,[episode(obs,1)])
    lost,_=update(cp,[episode(obs,-1)])
    assert metrics['actor_delta_l2']>0 and metrics['value_delta_l2']>0
    assert distribution(obs,won)[0][0]>p0>distribution(obs,lost)[0][0]
    assert cp.parameters==Parameters.initial()


def test_frozen_on_policy_and_phase_requirements(obs):
    cp=checkpoint();ep=episode(obs)
    for bad in (replace(ep,phase='final'),replace(ep,phase='selection'),replace(ep,checkpoint_sha256='1'*64),replace(ep,reward=None)):
        with pytest.raises(ValueError):update(cp,[bad])
    with pytest.raises(ValueError):update(cp,[ep,ep])
    with pytest.raises(ValueError):update(cp,[])


def test_frozen_opponent_hash_guard(tmp_path):
    from battlemind.environment import sha256
    from battlemind.reinforce_experiment import verify_opponents
    path=tmp_path/'opponent.json';save_checkpoint(path,Parameters.initial(),{})
    pool=({'checkpoint':str(path),'sha256':sha256(path)},)
    verify_opponents(pool)
    path.write_text('{}')
    with pytest.raises(ValueError,match='changed'):verify_opponents(pool)


def test_main_step_scale_is_finite_bounded_and_outcome_driven(obs):
    model,metrics=update(checkpoint(),[episode(obs)],30,.1)
    assert np.isfinite(np.asarray(model.actor)).all() and np.linalg.norm(model.actor)<=6
    assert metrics['actor_delta_l2']>0


def test_budget_exhaustion_and_idempotent_stop(tmp_path):
    now=[0.0]
    config={'games':{'training':24,'selection':0,'final':24},'seconds':{'training':130,'selection':10,'final':130,'overhead':30},'maximum_seconds':300,'maximum_games':48}
    l=Ledger(tmp_path,config,clock=lambda:now[0]);l.begin('training')
    i=l.reserve({'path':'training/cell'})
    assert l.data['phases']['final']['requested']==0
    assert l.data['phases']['training']['reserved']==24 and l.data['phases']['training']['requested']==0
    l.dispatch(i)
    with pytest.raises(ValueError):l.dispatch(i)
    with pytest.raises(ValueError):l.reserve({})
    now[0]=80;l.finish('stopped');before=(tmp_path/'ledger.json').read_bytes()
    now[0]=999;l.finish();assert before==(tmp_path/'ledger.json').read_bytes()
    assert l.data['phases']['training']['seconds']==80 and l.data['phases']['final']['requested']==0
    with pytest.raises(ValueError):Ledger(tmp_path,config)


def test_cap_is_not_reward_and_selection_does_not_reward_missingness():
    capped={'status':'truncated','winner':None}
    loss={'status':'completed','winner':'b'}
    assert selection_score([capped])==(0,-2)
    assert selection_score([loss])>selection_score([capped])
    assert not bootstrap({'initial':{},'selected':{}},1)['available']


def test_uncertainty_retains_caps_as_unknown_bounds():
    groups={arm:{name:[{'status':'completed','winner':'a'} for _ in range(48)]
        for name in ('random','max','v2','v5','c0','c6')} for arm in ('initial','selected')}
    groups['selected']['random'][0]={'status':'truncated','winner':None}
    report=bootstrap(groups,3)
    assert report['completed_reward_difference']==0
    assert report['all_requested_unknown_reward_bounds'][0]<0
    assert report['all_requested_unknown_reward_bounds'][1]==0


def test_softmax_model_errors_never_fallback(obs):
    for logits in (np.array([]),np.array([np.nan]),np.array([0.,-1000.])):
        with pytest.raises(ValueError):softmax(logits)
    with pytest.raises(ValueError):ReinforceAgent(checkpoint(),1).choose(replace(obs,legal_actions=()))


@pytest.mark.integration
def test_retained_reinforce_smoke_workflow():
    """Read real smoke evidence; collects zero additional test-suite games."""
    from battlemind.environment import ROOT
    from battlemind.reinforce_training import audit_run, trajectories
    path=ROOT/'runs/reinforce-smoke'
    if not path.exists():pytest.skip('Run the separately budgeted smoke specification first')
    result=json.loads((path/'summary.json').read_text())
    # Full source freeze is historical; compatible scorer/gradient semantics replay today.
    for record in result['ledger']['runs']:
        assert audit_run(path/record['path'])['ok']
    parent=load_checkpoint(path/'checkpoints/c0.json')
    episodes,targets=trajectories(path/'training/b1-vs-c0',parent,'training')
    params,metrics=update(parent,episodes,.3,.1)
    assert params==load_checkpoint(path/'checkpoints/c1.json').parameters
    assert len(episodes)==20 and sum(t['reward'] is None for t in targets)==4
    assert result['status']=='finished'
    assert result['updates']==1 and result['report']['phases']['training']['requested']==24
    assert load_checkpoint(path/'checkpoints/c0.json').parameters!=load_checkpoint(path/'selected.json').parameters
