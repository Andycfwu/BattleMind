"""Explicitly selected tests: real server games and pinned official-engine requests."""

import asyncio
from dataclasses import replace
import json
import logging
from pathlib import Path
import socket
import uuid

from poke_env.battle import Battle
import pytest

from battlemind.adapter import PublicTracker, snapshot
from battlemind.environment import ROOT, command, executable, inspect_server
from battlemind.reporting import report
from battlemind.runner import RunConfig, run

pytestmark = pytest.mark.integration


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def audit_run(output: Path, expected: int):
    summary = report(output)
    decisions = read_rows(output / "decisions.jsonl")
    battles = read_rows(output / "battles.jsonl")
    events = read_rows(output / "events.jsonl")
    assert summary["completed"] == expected
    assert len(battles) == expected
    assert summary["invalid_action_incidents"] == 0
    from battlemind.reporting import known_gen1_warning
    assert not any(e["kind"] in {"adapter_exception", "server_error", "client_log"}
                   and not known_gen1_warning(e) for e in events)
    assert len(decisions) == summary["decisions"] > 0
    submissions = {(e["match"], e["player"], e["request_id"]) for e in events if e["kind"] == "submitted"}
    assert len(submissions) == len(decisions)
    for row in decisions:
        obs = row["observation"]
        ids = {a["id"] for a in obs["legal_actions"]}
        assert ids == set(row["legal_mapping"])
        assert row["chosen_action"] in ids
        assert row["command"] == row["legal_mapping"][row["chosen_action"]]
        assert (row["match"], row["player"], obs["request_id"]) in submissions
        assert all(e["turn"] <= obs["turn"] for e in obs["public_history"])
        for mon in obs["opponent_revealed"]:
            assert mon["effective_stats"] is None and mon["hidden_moves"] is None
            assert mon["health"]["precision"] in {"public_scale", "fainted"}
            revealed = {event["values"][0] for event in obs["public_history"]
                        if event["kind"] == "move" and event["actor"] == f"opponent:{mon['slot']}"}
            assert set(mon["moves"]) == revealed
    for battle in battles:
        terminals = {e["player"]: e["result"] for e in events if e["kind"] == "terminal" and e["match"] == battle["match"]}
        assert battle["terminal_results"] == terminals
    if (output / "privileged/labels.jsonl").exists():
        from battlemind.labels import audit_labels
        audit_labels(output)
        assert "CRASH:" not in (output / "server.log").read_text()


def test_real_server_smoke():
    port = free_port()
    output = ROOT / "runs" / ("integration-" + uuid.uuid4().hex[:10])
    config = replace(RunConfig(), port=port)
    result = asyncio.run(run(config, output, start_server=True))
    assert result["completed"] == 2, result
    audit_run(output, 2)
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "Managed server leaked after run"


@pytest.mark.parametrize("changes, status", [({"turn_cap": 1}, "truncated"), ({"timeout": 0.01}, "timeout")])
def test_real_limits_are_never_wins(changes, status):
    output = ROOT / "runs" / (f"integration-{status}-" + uuid.uuid4().hex[:10])
    config = replace(RunConfig(), battles=1, port=free_port(), **changes)
    result = asyncio.run(run(config, output, start_server=True))
    assert result[status] == 1, result
    assert result["completed"] == result["a_wins"] == result["b_wins"] == 0
    assert read_rows(output / "battles.jsonl")[0]["winner"] is None


def test_official_gen1_requests_pass_real_wrapper_and_adapter():
    server = ROOT / ".local/pokemon-showdown"
    inspect_server(server, [ROOT / p for p in RunConfig().teams], 8000)
    cases = json.loads(command([executable("node"), str(ROOT / "scripts/probe-gen1.cjs")], server))
    for name, request in cases.items():
        tracker = PublicTracker()
        tracker.request(request)
        battle = Battle("battle-gen1ou-probe", "ProbeA", logging.getLogger("probe"), gen=1)
        battle.parse_request(request)
        obs, mapping = snapshot(battle, tracker)
        expected = "fight" if name in {"sleep", "partial_trap"} else name
        if name == "forced_switch":
            assert all(a.kind == "switch" for a in obs.legal_actions)
        else:
            assert f"engine:{expected}" in mapping
        if name == "partial_trap":
            assert any(a.kind == "switch" for a in obs.legal_actions)
            assert not obs.trapped
        assert obs.gen1_derived_counters is None


def test_official_engine_commit_contract_and_unexecuted_move():
    server = ROOT / ".local/pokemon-showdown"
    result = json.loads(command([executable("node"), str(ROOT / "scripts/probe-labels.cjs")], server))
    assert result["passed"] and not result["growl_announced"]


def test_new_team_pool_real_matches_and_labels():
    config = RunConfig(agent_a="gen1-heuristic", agent_b="random", battles=4, port=free_port(),
                       teams=("configs/teams/ou-v2-c.txt", "configs/teams/ou-v2-d.txt"))
    output = ROOT / "runs" / ("integration-m2-" + uuid.uuid4().hex[:10])
    result = asyncio.run(run(config, output, start_server=True))
    assert result["completed"] == 4, result
    audit_run(output, 4)
    labels = read_rows(output / "privileged/labels.jsonl")
    assert any(r["intended_kind"] == "forced_replacement" for r in labels)
    assert any(r["intended_kind"] == "voluntary_switch" for r in labels)
    assert any(r["execution"]["status"] == "move_announced" for r in labels)
    assert result["labels"]["verified_intended_choices"] > 0


def test_separate_server_copies_matching_commit_evidence():
    from battlemind.environment import LocalServer
    from battlemind.labels import audit_labels

    output = ROOT / "runs" / ("integration-separate-" + uuid.uuid4().hex[:10])
    config = replace(RunConfig(), battles=1, port=free_port())
    log = ROOT / ".local" / ("test-separate-" + uuid.uuid4().hex[:10] + ".log")

    async def exercise():
        server = ROOT / config.showdown
        async with LocalServer(server, config.port, log, server / "logs"):
            return await run(config, output, start_server=False)

    result = asyncio.run(exercise())
    assert result["completed"] == 1 and result["labels"]["verified_intended_choices"] > 0
    assert (output / "privileged/000-engine.json").is_file()
    assert result["resources"]["managed_server_peak_sampled_rss_bytes"] is None
    assert audit_labels(output)["ok"]


def test_v3_audited_dataset_frozen_counts_and_real_policy_pipeline():
    from battlemind.dataset import build_dataset, fit_predictor
    from battlemind.environment import sha256
    from battlemind.prediction_report import audit_predictions, evaluate_predictor

    root = ROOT / "runs" / ("integration-v3-" + uuid.uuid4().hex[:10])
    base = root / "development-battles"
    config = replace(RunConfig(), battles=4, port=free_port())
    assert asyncio.run(run(config, base, start_server=True))["completed"] == 4
    dataset = root / "development-data"
    build_dataset([base], dataset)
    with pytest.raises(ValueError, match="Duplicate run identity"):
        build_dataset([base, base], root / "duplicate-data")
    model = root / "counts.json"
    fit_predictor(dataset, model)
    original_hash = sha256(model)
    evaluation = root / "evaluation-battles"
    config = replace(config, agent_a="switch-constant", agent_b="switch-context", predictor=str(model), port=free_port())
    result = asyncio.run(run(config, evaluation, start_server=True))
    assert result["completed"] == 4, result
    audit_run(evaluation, 4)
    assert audit_predictions(evaluation)["prediction_decisions"] == result["decisions"]
    fresh = root / "evaluation-data"
    build_dataset([evaluation], fresh, role="evaluation")
    quality = evaluate_predictor(fresh, model, root / "probability-report", "evaluation")
    assert quality["balance"]["examples"] > 0
    assert 0 <= quality["metrics"]["conditional"]["brier"] <= 1
    assert sha256(model) == original_hash == sha256(evaluation / "predictor.json")


def test_v4_real_record_training_frozen_inference_and_audit():
    from battlemind.supervised_data import build_supervised_dataset, load_bundle
    from battlemind.supervised_training import train_bundle
    from battlemind.supervised_report import evaluate_bundle
    from battlemind.prediction_report import audit_predictions
    from battlemind.environment import sha256

    root = ROOT / "runs" / ("integration-v4-" + uuid.uuid4().hex[:10])
    config = replace(RunConfig(), agent_a="switch-moderate", agent_b="random", battles=4, port=free_port())
    recorded = root / "recorded"
    result = asyncio.run(run(config, recorded, start_server=True))
    assert result["completed"] == 4, result
    audit_run(recorded, 4)
    data = root / "development-data"
    manifest = build_supervised_dataset([recorded], data)
    assert manifest["primary_balance"]["development_fit"]["switches"] > 0
    model = root / "model.json"
    train_bundle(data, model)
    frozen = sha256(model)
    _, bundle = load_bundle(model)
    assert bundle.logistic.regularization in {0.01, 0.1, 1.0}
    evaluation = root / "evaluation"
    config = replace(config, agent_a="switch-logistic", agent_b="switch-context", predictor=str(model), port=free_port())
    result = asyncio.run(run(config, evaluation, start_server=True))
    assert result["completed"] == 4, result
    audit_run(evaluation, 4)
    assert audit_predictions(evaluation)["prediction_decisions"] == result["decisions"]
    fresh = root / "evaluation-data"
    build_supervised_dataset([evaluation], fresh, role="evaluation")
    quality = evaluate_bundle(fresh, model, root / "quality", "evaluation")
    assert quality["balance"]["examples"] > 0
    assert all(0 <= m["brier"] <= 1 for m in quality["metrics"].values())
    assert sha256(model) == frozen == sha256(evaluation / "predictor.json")


def test_v5_real_selfplay_outcome_update_checkpoint_and_frozen_evaluation():
    from battlemind.environment import sha256
    from battlemind.learned_policy import PolicyParameters, save_checkpoint, load_checkpoint
    from battlemind.policy_search import propose, outcome_update
    from battlemind.prediction_report import audit_predictions
    from battlemind.supervised_data import load_bundle

    root = ROOT / "runs" / ("integration-v5-" + uuid.uuid4().hex[:10])
    predictor_path = ROOT / "models/v4-supervised.json"
    _, bundle = load_bundle(predictor_path)
    initial = root / "initial.json"
    save_checkpoint(initial, PolicyParameters(), bundle, {"kind": "integration-initial"})
    original_hash = sha256(predictor_path)
    initial_hash = sha256(initial)
    proposal = propose(PolicyParameters(), 51501)
    records = {}
    for sign in ("plus", "minus"):
        checkpoint = root / f"{sign}.json"
        save_checkpoint(checkpoint, getattr(proposal, sign), bundle, {"kind": "integration-proposal", "sign": sign})
        config = replace(RunConfig(), battles=4, agent_a="learned-score", agent_b="learned-score",
            predictor=str(predictor_path), checkpoint_a=str(checkpoint), checkpoint_b=str(initial), port=free_port())
        path = root / sign
        result = asyncio.run(run(config, path, start_server=True))
        assert result["completed"] == 4, result
        audit_run(path, 4)
        assert audit_predictions(path)["prediction_decisions"] == result["decisions"]
        records[sign] = read_rows(path / "battles.jsonl")
    parameters, update = outcome_update(proposal, records["plus"], records["minus"], 4)
    checkpoint = root / "updated.json"
    save_checkpoint(checkpoint, parameters, bundle, {"kind": "integration-outcome-update", **update})
    frozen_hash = sha256(checkpoint)
    config = replace(config, checkpoint_a=str(checkpoint), port=free_port())
    path = root / "evaluation"
    result = asyncio.run(run(config, path, start_server=True))
    assert result["completed"] == 4, result
    audit_run(path, 4)
    assert audit_predictions(path)["prediction_decisions"] == result["decisions"]
    assert sha256(checkpoint) == frozen_hash and load_checkpoint(checkpoint, bundle)[1].parameters == parameters
    assert sha256(predictor_path) == original_hash and sha256(initial) == initial_hash


def test_v6_real_public_encounter_memory_replay_and_privileged_independence(tmp_path):
    import shutil
    from battlemind.adaptation_experiment import artifacts, PREDICTOR, CHECKPOINT, CONFIG
    from battlemind.environment import sha256
    from battlemind.labels import audit_labels
    from battlemind.memory_runtime import EncounterController
    from battlemind.memory_audit import replay_cell
    from battlemind.opponent_memory import ObserverMemory
    from battlemind.prediction_report import audit_predictions

    root = ROOT / "runs" / ("integration-v6-" + uuid.uuid4().hex[:10])
    bundle, checkpoint = artifacts()
    frozen_hashes = sha256(PREDICTOR), sha256(CHECKPOINT)
    manager, replay = ObserverMemory(), ObserverMemory()
    teams = tuple(json.loads(CONFIG.read_text())["teams"])
    all_decisions = []
    for i, target in enumerate(("switch-active", "max-base-power")):
        path = root / f"encounters-{i}"
        controller = EncounterController(manager, f"opaque-{i}", "one-observer", "individual", bundle)
        config = RunConfig(agent_a="learned-score", agent_b=target, predictor=str(PREDICTOR), checkpoint_a=str(CHECKPOINT),
            teams=teams, schedule_offset=i * 4, battles=4, port=free_port())
        result = asyncio.run(run(config, path, start_server=True, memory_controller=controller))
        assert result["completed"] == 4 and result["invalid_action_incidents"] == 0, result
        assert audit_predictions(path)["prediction_decisions"] == len(read_rows(path / "privileged/attempts/000-a.jsonl")) + sum(
            len(read_rows(path / f"privileged/attempts/{m:03d}-a.jsonl")) for m in range(1, 4))
        rebuilt = replay_cell(path, replay, bundle, checkpoint)
        all_decisions.extend(rebuilt["decisions"])
        assert replay.pooled == manager.pooled and replay.sessions == manager.sessions
    assert any(r["probabilities"]["individual"] != r["probabilities"]["none"] for r in all_decisions)
    assert manager.next_ordinal == 8 and len(manager.sessions) == 2
    assert (sha256(PREDICTOR), sha256(CHECKPOINT)) == frozen_hashes
    # Corrupt only a COPY of newly generated test evidence, never historical artifacts.
    copied = tmp_path / "tampered"
    shutil.copytree(root / "encounters-0", copied)
    engine_path = copied / read_rows(copied / "battles.jsonl")[0]["engine_record"]["path"]
    data = json.loads(engine_path.read_text())
    data["private_v6_test"] = {"team": "hidden replacement", "rng": "altered"}
    engine_path.write_text(json.dumps(data))
    labels = read_rows(copied / "privileged/labels.jsonl")
    labels[0]["voluntary_switch_target"] = 1
    (copied / "privileged/labels.jsonl").write_text("\n".join(json.dumps(r) for r in labels) + "\n")
    assert replay_cell(copied, ObserverMemory(), bundle, checkpoint) == replay_cell(root / "encounters-0", ObserverMemory(), bundle, checkpoint)
    with pytest.raises(ValueError):
        audit_labels(copied)
