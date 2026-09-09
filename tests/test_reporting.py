import json

import pytest

from battlemind.reporting import report, summarize
from battlemind.runner import RunConfig, policy_seed


def test_summary_excludes_caps_and_crashes_even_if_forfeit_has_winner(tmp_path):
    rows = [{"match": i, "status": status, "winner": winner, "invalid_actions": int(status == "crash")}
            for i, (status, winner) in enumerate([("completed", "a"), ("completed", "b"), ("completed", "draw"),
                ("truncated", "a"), ("timeout", "b"), ("crash", "a"), ("not_started", None)])]
    result = summarize(rows, 7)
    assert result["completed"] == 3
    assert result["a_wins"] == result["b_wins"] == result["draws"] == 1
    assert result["completed_game_win_rate_a"] == 1 / 3
    assert result["invalid_action_incidents"] == 1
    assert result["unrecorded"] == 0
    (tmp_path / "run.json").write_text(json.dumps({"config": {"battles": 7}}))
    (tmp_path / "battles.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    assert report(tmp_path) == result
    assert json.loads((tmp_path / "summary.json").read_text()) == result
    assert (tmp_path / "summary.csv").read_text().count("\n") == 2


def test_summary_handles_no_games_and_detects_duplicates():
    assert summarize([], 2)["completed_game_win_rate_a"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        summarize([{"match": 0}, {"match": 0}], 2)


@pytest.mark.parametrize("kwargs", [{"concurrency": 2}, {"battles": 0}, {"turn_cap": 0},
                                    {"timeout": 0}, {"run_timeout": 9999}, {"format": "gen9ou"},
                                    {"port": 80}, {"agent_a": "unknown"}])
def test_config_rejects_unsupported_or_unbounded_runs(kwargs):
    with pytest.raises(ValueError):
        RunConfig(**kwargs).validate()


def test_policy_seeds_are_stable_and_separate():
    assert policy_seed(42, 0, "a") == policy_seed(42, 0, "a")
    assert len({policy_seed(42, i, s) for i in range(20) for s in ("a", "b")}) == 40


def test_intervals_and_narrow_warning_classification():
    from battlemind.reporting import known_gen1_warning, wilson_interval
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(24, 24)
    assert 0.86 < low < 0.87 and abs(high - 1) < 1e-10
    event = {"kind": "client_log", "level": "WARNING", "message":
             "Unmanaged move message format received - cleaned up message ['', 'move', 'p2a: Cloyster', 'Clamp', 'p1a: Gengar', '[from] Clamp'] in battle battle-gen1ou-20 turn 21"}
    assert known_gen1_warning(event)
    assert not known_gen1_warning({**event, "message": "Unexpected error"})
    assert not known_gen1_warning({**event, "level": "ERROR"})
