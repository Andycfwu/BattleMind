"""Offline regressions for the two retained-evidence audit defects."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from battlemind.adapter import snapshot_request
from battlemind.environment import ROOT, sha256
from battlemind.reinforce import Parameters, ReinforceAgent, load_checkpoint, save_checkpoint
from battlemind.reinforce_experiment import build_report, report_experiment


@pytest.mark.parametrize('head', ['actor', 'value'])
def test_loader_rejects_numeric_string_at_load(tmp_path, head):
    path = tmp_path / 'model.json'
    save_checkpoint(path, Parameters.initial(), {})
    data = json.loads(path.read_text())
    if head == 'actor':
        data['actor'][0][0] = '0.1'
    else:
        data['value'][0] = '0.1'
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises((TypeError, ValueError), match='numeric|number'):
        load_checkpoint(path)
    assert path.read_bytes() == before


@pytest.fixture
def comparison(tmp_path, monkeypatch, turn_request, tracker):
    """Real report assembly over synthetic probabilities, never battle fixtures."""
    from battlemind import reinforce, reinforce_experiment
    obs = snapshot_request(turn_request, 1, tracker)[0]
    obs = replace(obs, legal_actions=obs.legal_actions[:2])
    initial = save_checkpoint(tmp_path / 'checkpoints/c0.json', Parameters.initial(), {})
    actor = [list(r) for r in Parameters.initial().actor]
    actor[0][0] = .1
    selected = save_checkpoint(tmp_path / 'selected.json', Parameters(tuple(map(tuple, actor)), initial.parameters.value), {})

    def distribution(obs, params):
        probabilities = np.array([.5, .5]) if params == initial.parameters else np.array([.6, .4])
        return probabilities, 0.0, np.log(probabilities), None, None

    monkeypatch.setattr(reinforce_experiment, 'distribution', distribution)
    monkeypatch.setattr(reinforce, 'distribution', distribution)
    cell = tmp_path / 'final/initial-r0-vs-fixture'
    cell.mkdir(parents=True)
    (cell / 'battles.jsonl').write_text(json.dumps({'match': 0, 'status': 'completed', 'winner': 'a'})+'\n')
    row = {'player': 'a', 'decision_id': 'synthetic:1', 'snapshot_sha256': '0'*64,
           'observation': asdict(obs), 'policy_evaluation': {'draw': .5}}
    resources = dict(python_cpu_seconds=0.0, managed_server_cpu_seconds_last_sample=None,
                     python_peak_sampled_rss_bytes=0, managed_server_peak_sampled_rss_bytes=None)
    ledger = {'runs': [{'path': cell.relative_to(tmp_path).as_posix(), 'phase': 'final', 'status': 'recorded',
                       'requested': 1, 'run_id': '0'*64, 'opponent': {'identity': 'fixture'},
                       'summary': {'resources': resources, 'labels': dict(attempts=0, verified_intended_choices=0, unknown_intended_choices=0)}}],
              'phases': {phase: {'reserved': int(phase == 'final')} for phase in ('training', 'selection', 'final')}}
    config = {'games': dict(training=0, selection=0, final=1), 'seed': 42}

    def write_row():
        (cell/'decisions.jsonl').write_text(json.dumps(row)+'\n')

    def report():
        write_row()
        return build_report(tmp_path, ledger, config)

    return SimpleNamespace(root=tmp_path, cell=cell, row=row, obs=obs, initial=initial,
                           selected=selected, ledger=ledger, config=config, report=report)


def test_comparison_exact_boundary_matches_actual_sampler(comparison):
    result = comparison.report()
    agent = ReinforceAgent(comparison.initial, 0)
    agent.rng = SimpleNamespace(random=lambda: .5)
    actual = agent.act(comparison.obs)
    recorded = json.loads((comparison.root/'decision-differences.jsonl').read_text())
    assert actual.chosen_action == comparison.obs.legal_actions[1].id
    assert recorded['initial_choice'] == actual.chosen_action
    assert recorded['selected_choice'] == comparison.obs.legal_actions[0].id
    assert result['same_snapshot'] == {'examples': 1, 'argmax_changed': 0, 'shared_draw_changed': 1}


@pytest.mark.parametrize('draw', [0.0, np.nextafter(.5, 0), np.nextafter(.5, 1), np.nextafter(1.0, 0)])
def test_comparison_other_valid_draws_match_sampler(comparison, draw):
    comparison.row['policy_evaluation']['draw'] = float(draw)
    comparison.report()
    recorded = json.loads((comparison.root/'decision-differences.jsonl').read_text())
    for model, field in ((comparison.initial, 'initial_choice'), (comparison.selected, 'selected_choice')):
        agent = ReinforceAgent(model, 0)
        agent.rng = SimpleNamespace(random=lambda: float(draw))
        assert recorded[field] == agent.act(comparison.obs).chosen_action


def test_report_unavailable_comparison_does_not_invent_zero_difference(comparison):
    (comparison.root/'selected.json').unlink()  # Synthetic temporary file only.
    report = comparison.report()
    assert report['same_snapshot'] == {'examples': 0}
    assert report['uncertainty']['available'] is False
    assert report['phases']['training']['completed_game_win_rate_a'] is None
    assert report['phases']['training']['requested'] == 0


def test_read_only_report_returns_stored_values_without_writes(tmp_path):
    values = {'report': {'valid_zero': 0.0, 'unavailable': None}, 'ledger': {}}
    source = tmp_path/'summary.json'
    source.write_text(json.dumps(values))
    before = sha256(source)
    assert report_experiment(tmp_path)['report'] == values['report']
    assert report_experiment(tmp_path)['report'] == values['report']
    assert sha256(source) == before
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize('head', ['actor', 'value'])
@pytest.mark.parametrize('bad', [True, None, {}, [], 'NaN', float('nan'), float('inf'), 100.0])
def test_loader_rejects_malformed_nonfinite_or_out_of_bounds_coefficients(tmp_path, head, bad):
    path = tmp_path/'model.json'
    save_checkpoint(path, Parameters.initial(), {})
    data = json.loads(path.read_text())
    if head == 'actor':data['actor'][0][0] = bad
    else:data['value'][0] = bad
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises((TypeError, ValueError)):load_checkpoint(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('revision', ['current', 'original'])
def test_valid_integer_and_float_coefficients_load_without_coercion(tmp_path, revision):
    path = tmp_path/'model.json'
    save_checkpoint(path, Parameters.initial(), {})
    data = json.loads(path.read_text())
    data['actor'][0][0] = 1
    data['value'][0] = .1
    if revision == 'original':
        data['compatibility'] = json.loads((ROOT/'configs/reinforce-loader-compatibility.json').read_text())['original_checkpoint_compatibility']
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    loaded = load_checkpoint(path)
    assert type(loaded.parameters.actor[0][0]) is int
    assert loaded.parameters.value[0] == .1
    assert path.read_bytes() == before


@pytest.mark.parametrize('field', ['version', 'snapshot', 'actor_shape', 'state_features', 'versions_sha256',
                                  'reinforce.py', 'heuristic.py', 'schema.py'])
def test_legacy_compatibility_does_not_accept_other_metadata(tmp_path, field):
    path = tmp_path/'legacy.json'
    save_checkpoint(path, Parameters.initial(), {})
    data = json.loads(path.read_text())
    data['compatibility'] = json.loads((ROOT/'configs/reinforce-loader-compatibility.json').read_text())['original_checkpoint_compatibility']
    if field.endswith('.py'):data['compatibility']['source_hashes'][field] = 'f'*64
    else:data['compatibility'][field] = 'incompatible'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Incompatible'):load_checkpoint(path)


@pytest.mark.parametrize('changed_source', ['reinforce.py', 'heuristic.py', 'schema.py'])
def test_legacy_compatibility_requires_exact_reviewed_runtime(tmp_path, monkeypatch, changed_source):
    from battlemind import reinforce
    path = tmp_path/'legacy.json'
    save_checkpoint(path, Parameters.initial(), {})
    data = json.loads(path.read_text())
    data['compatibility'] = json.loads((ROOT/'configs/reinforce-loader-compatibility.json').read_text())['original_checkpoint_compatibility']
    path.write_text(json.dumps(data))
    runtime = reinforce.compatibility()
    runtime['source_hashes'][changed_source] = 'f'*64
    monkeypatch.setattr(reinforce, 'compatibility', lambda: runtime)
    with pytest.raises(ValueError, match='Incompatible'):load_checkpoint(path)


@pytest.mark.parametrize('evaluation', [None, {}])
def test_comparison_missing_draw_is_an_error_not_zero(comparison, evaluation):
    comparison.row['policy_evaluation'] = evaluation
    with pytest.raises(ValueError, match='Missing recorded policy draw'):comparison.report()


@pytest.mark.parametrize('draw', [None, '0.5', True, float('nan'), float('inf'), -.1, 1.0])
def test_comparison_invalid_draw_is_an_error_not_a_choice(comparison, draw):
    comparison.row['policy_evaluation']['draw'] = draw
    with pytest.raises(ValueError, match='Invalid recorded policy draw'):comparison.report()


def test_invalid_checkpoint_is_not_reported_as_unavailable(comparison):
    path = comparison.root/'selected.json'
    data = json.loads(path.read_text());data['value'][0] = '0.1'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='numbers'):comparison.report()


def test_missing_battle_record_remains_missing_not_an_outcome(comparison):
    (comparison.cell/'battles.jsonl').unlink()
    result = comparison.report()
    assert result['phases']['final']['requested'] == 1
    assert result['phases']['final']['unrecorded'] == 1
    assert result['phases']['final']['completed'] == 0
    assert result['phases']['final']['completed_game_win_rate_a'] is None
    assert result['uncertainty']['available'] is False


def test_historical_full_source_audit_is_not_bypassed(tmp_path, monkeypatch):
    from battlemind import reinforce_experiment
    summary = {'ledger': {'runs': [], 'battle_partitions': {}}}
    for name, value in [('summary.json', summary), ('artifact-hashes.json', {}),
                        ('freeze.json', {'source': {'old.py': 'a'*64}}), ('updates.json', [])]:
        (tmp_path/name).write_text(json.dumps(value))
    before = {p.name:sha256(p) for p in tmp_path.iterdir()}
    monkeypatch.setattr(reinforce_experiment, 'source_manifest', lambda: {'new.py':'b'*64})
    audit = report_experiment(tmp_path, audit=True)['audit']
    assert audit['ok'] is False
    assert 'historical source needed' in audit['errors'][0]
    assert {p.name:sha256(p) for p in tmp_path.iterdir()} == before
