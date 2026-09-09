"""Clock and request regressions; fixtures never stand in for battle evidence."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from battlemind.adaptation_ledger import AdaptationLedger, request_accounting
from battlemind.adaptation_report import build_adaptation_report
from battlemind.environment import ROOT, sha256, source_manifest


def small_config():
    return {"total_games": 8, "total_seconds": 60, "overhead_seconds": 20,
        "games": {"development": 4, "final": 4}, "seconds": {"development": 20, "final": 20}}


def complete_cell(ledger, phase, identity):
    ledger.begin(phase)
    i = ledger.reserve({"group": 0}, 4)
    ledger.dispatch(i)
    ledger.record(i, identity, [{"match": n, "status": "completed"} for n in range(4)], {})


def test_failed_phase_stop_and_finish_are_idempotent(tmp_path):
    now = [0.0]
    ledger = AdaptationLedger(tmp_path, small_config(), clock=lambda: now[0])
    now[0] = 2
    ledger.begin("development")
    now[0] = 8
    ledger.finish("explicit budget stop")
    frozen = deepcopy(ledger.state)
    saved = (tmp_path / "ledger.json").read_bytes()
    now[0] = 12
    ledger.finish("different error must not replace first stop")
    ledger.finish_phase()
    assert ledger.state == frozen and (tmp_path / "ledger.json").read_bytes() == saved
    assert ledger.state["phases"]["development"]["consumed_seconds"] == 6
    assert ledger.state["timing"]["collection_stop_elapsed_seconds"] == 8
    assert ledger.state["phases"]["final"]["consumed_seconds"] == 0
    ledger.finalize()
    assert ledger.state["timing"] == {"collection_stop_elapsed_seconds": 8,
        "setup_seconds": 2, "reporting_audit_seconds": 4, "overhead_seconds": 6, "finalized": True}
    assert ledger.state["consumed_seconds"] == 12
    saved = (tmp_path / "ledger.json").read_bytes()
    now[0] = 1000
    ledger.finish(); ledger.finalize(); ledger.save()
    assert (tmp_path / "ledger.json").read_bytes() == saved


def test_successful_phase_and_report_clocks_are_separate(tmp_path):
    now = [0.0]
    ledger = AdaptationLedger(tmp_path, small_config(), clock=lambda: now[0])
    complete_cell(ledger, "development", "development")
    now[0] = 4
    ledger.finish_phase()
    now[0] = 6
    ledger.finish_phase()
    complete_cell(ledger, "final", "final")
    now[0] = 11
    ledger.finish_phase(); ledger.finish()
    now[0] = 15
    ledger.finalize()
    assert ledger.state["status"] == "finished"
    assert [p["consumed_seconds"] for p in ledger.state["phases"].values()] == [4, 5]
    assert ledger.state["timing"]["setup_seconds"] == 2
    assert ledger.state["timing"]["reporting_audit_seconds"] == 4
    assert ledger.state["consumed_seconds"] == 15


def test_reserved_capacity_is_not_a_dispatched_request_and_is_not_refunded(tmp_path):
    ledger = AdaptationLedger(tmp_path, small_config())
    ledger.begin("development")
    i = ledger.reserve({"group": 0}, 4)
    assert ledger.state["reserved_games"] == 4 and ledger.state["requested_games"] == 0
    assert request_accounting(8, ledger.state["runs"], []) == {
        "planned_games": 8, "reserved_games": 4, "requested_games": 0,
        "reserved_not_requested_games": 4, "never_requested_games": 8,
        "recorded_games": 0, "completed_games": 0, "started_games": 0,
        "never_started_games": 8, "missing_requested_records": 0, "start_status_unknown_games": 0}
    with pytest.raises(ValueError):
        ledger.reserve({}, 1)
    ledger.finish("failed before dispatch")
    with pytest.raises(ValueError):
        ledger.dispatch(i)
    with pytest.raises(ValueError):
        ledger.begin("development")


def test_partial_dispatched_records_keep_unknown_starts_separate(tmp_path):
    ledger = AdaptationLedger(tmp_path, small_config())
    ledger.begin("development")
    i = ledger.reserve({"group": 0}, 4)
    ledger.dispatch(i)
    rows = [{"match": 0, "status": "completed"}, {"match": 1, "status": "not_started"}]
    ledger.record(i, "partial", rows, {})
    with pytest.raises(ValueError, match="Phase incomplete"):
        ledger.finish_phase()
    ledger.finish("missing records")
    a = request_accounting(8, ledger.state["runs"], rows)
    assert a["requested_games"] == 4 and a["completed_games"] == 1
    assert a["never_started_games"] == 5 and a["missing_requested_records"] == 2
    assert a["start_status_unknown_games"] == 2
    assert ledger.state["phases"]["final"]["requested_games"] == 0


def test_overhead_cannot_borrow_unused_phase_budget(tmp_path):
    now = [0.0]
    ledger = AdaptationLedger(tmp_path, small_config(), clock=lambda: now[0])
    complete_cell(ledger, "development", "dev")
    ledger.finish_phase()
    complete_cell(ledger, "final", "final")
    ledger.finish_phase(); ledger.finish()
    now[0] = 21  # Most phase capacity is unused, but the overhead allocation is 20.
    ledger.finalize()
    assert ledger.state["status"] == "failed" and "overhead" in ledger.state["failure"]


def test_full_report_zero_request_final_arms_and_read_only_failed_timing(tmp_path, monkeypatch):
    from battlemind import adaptation_experiment as experiment
    config = json.loads(experiment.REPAIR_CONFIG.read_text())
    now = [0.0]
    ledger = AdaptationLedger(tmp_path, config, clock=lambda: now[0])
    ledger.begin("development")
    ledger.reserve(next(iter(experiment.group_schedule(config, "development", 0))), 4)
    now[0] = 406
    ledger.finish("reservation guard exhausted")
    ledger.finalize()
    freeze = {"version": "v6-freeze-2", "config": config,
        "config_path": "configs/v6-acceptance-repair.json", "spec_path": "docs/V6-ACCEPTANCE-REPAIR.md",
        "config_sha256": sha256(experiment.REPAIR_CONFIG), "spec_sha256": sha256(experiment.REPAIR_SPEC),
        "source": source_manifest()}
    (tmp_path / "freeze.json").write_text(json.dumps(freeze))
    # No policy is evaluated: isolate empty/failed accounting from retained model availability.
    monkeypatch.setattr(experiment, "artifacts", lambda *args: (SimpleNamespace(sha256="predictor"), SimpleNamespace(sha256="checkpoint")))
    before = (tmp_path / "ledger.json").read_bytes()
    report = build_adaptation_report(tmp_path)
    now[0] = 10000
    assert build_adaptation_report(tmp_path) == report
    assert (tmp_path / "ledger.json").read_bytes() == before
    assert report["status"] == "failed" and not report["audit"]["ok"]
    assert report["phases"]["development"]["consumed_seconds"] == 406
    for arm in report["final_battles"].values():
        assert arm["overall"]["requested"] == arm["overall"]["unrecorded"] == 0
        assert arm["overall"]["a_wins"] == arm["overall"]["b_wins"] == 0
        assert arm["overall"]["accounting"]["planned_games"] == 192
        assert arm["overall"]["accounting"]["never_started_games"] == 192
    assert report["accounting"]["reserved_games"] == 4 and report["accounting"]["requested_games"] == 0


def test_replacement_rejects_scientific_tuning():
    from battlemind.adaptation_experiment import REPAIR_CONFIG, validate_repair_config
    config = json.loads(REPAIR_CONFIG.read_text())
    for mutate in (lambda c: c["memory"].update(prior_encounters=4),
        lambda c: c.update(targets=["random", "switch-active"]),
        lambda c: c.update(policy_seed_base=1), lambda c: c.update(total_seconds=1801)):
        changed = deepcopy(config)
        mutate(changed)
        with pytest.raises(ValueError):
            validate_repair_config(changed)
