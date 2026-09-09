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
