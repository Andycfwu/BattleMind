"""Offline estimator tests only; independent of retained Pokémon win rates."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('contract_math',Path(__file__).resolve().parents[1]/'diagnostics/trajectory_contract_math.py')
math=importlib.util.module_from_spec(spec)
spec.loader.exec_module(math)


def test_one_to_one_matches_finite_differences():
    c=math.cases()['one_to_one']
    np.testing.assert_allclose(c['estimator'],c['finite_difference'],atol=1e-9)


def test_many_to_one_sampled_and_marginal_estimators_agree():
    c=math.cases()['many_to_one']
    for name in ('sampled_id_estimator','marginal_estimator'):
        np.testing.assert_allclose(c[name],c['finite_difference'],atol=1e-9)
    assert not np.allclose(c['wrong_canonical_estimator'],c['finite_difference'])


def test_hidden_state_dependent_forcing_and_singleton():
    c=math.cases()['state_dependent_forcing']
    np.testing.assert_allclose(c['estimator'],c['finite_difference'],atol=1e-9)
    np.testing.assert_allclose(c['all_aliases_forced'],0,atol=1e-15)
    assert c['singleton']==[0.]


def test_rejection_is_valid_only_with_known_transition_contract():
    c=math.cases()['rejection']
    np.testing.assert_allclose(c['estimator'],c['finite_difference'],atol=1e-9)
    assert not np.allclose(*c['missing_evidence_worlds'])


@pytest.mark.parametrize('draw,expected',[(0.,0),(.25,1),(.5,2),(np.nextafter(.25,0),0),(.999,2)])
def test_actual_sampler_strict_cdf_boundaries(monkeypatch,draw,expected):
    import battlemind.reinforce as rf
    from types import SimpleNamespace
    p=np.array([.25,.25,.5])
    monkeypatch.setattr(rf,'distribution',lambda *args:(p,0.,np.log(p),None,None))
    cp=rf.Checkpoint(rf.Parameters.initial(),'0'*64)
    policy=rf.ReinforceAgent(cp,7)
    policy.rng=SimpleNamespace(random=lambda:draw)
    obs=SimpleNamespace(legal_actions=tuple(SimpleNamespace(id=f'move:{i}') for i in range(3)))
    assert policy.act(obs).chosen_action==f'move:{expected}'


def test_action_dependent_exclusion_changes_estimator_and_baseline_cancellation():
    c=math.cases()['exclusion']
    assert not np.allclose(c['full'],c['filtered'])
    assert not np.allclose(c['filtered'],c['conditional_objective_gradient'])
    np.testing.assert_allclose(c['full'],c['full_with_baseline'])
    assert not np.allclose(c['filtered'],c['filtered_with_baseline'])


def test_verified_prefix_with_final_reward_omits_tail_gradient():
    c=math.cases()['verified_prefix']
    assert c['terminal_reward_known']
    assert c['full']==pytest.approx(c['finite_difference'],abs=1e-9)
    assert c['prefix_only']!=pytest.approx(c['full'])
