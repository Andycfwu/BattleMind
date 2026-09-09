"""The predeclared V6 public-memory experiment. No training/optimization imports."""

from dataclasses import asdict
import json
from pathlib import Path
import time

from .adaptation import ARMS
from .adaptation_ledger import AdaptationLedger
from .dataset import write_json
from .environment import ROOT, sha256, source_manifest
from .labels import audit_labels, read_jsonl
from .learned_policy import load_checkpoint
from .memory_runtime import EncounterController
from .opponent_memory import ObserverMemory, digest, PRIOR, MIN_ENCOUNTERS, MIN_EXAMPLES, MAX_ADJUSTMENT, FLOOR
from .runner import RunConfig, run
from .supervised_data import load_bundle

CONFIG = ROOT / "configs/v6-experiment.json"
SPEC = ROOT / "docs/V6-EXPERIMENT.md"
PREDICTOR = ROOT / "models/v4-supervised.json"
CHECKPOINT = ROOT / "runs/v5-acceptance/selected.json"
REPAIR_CONFIG = ROOT / "configs/v6-acceptance-repair.json"
REPAIR_SPEC = ROOT / "docs/V6-ACCEPTANCE-REPAIR.md"


def artifacts(predictor=PREDICTOR, checkpoint=CHECKPOINT):
    config = json.loads(CONFIG.read_text())
    for path, key in ((predictor, "predictor_sha256"), (checkpoint, "checkpoint_sha256")):
        if not path.is_file():
            raise ValueError(f"Required historical artifact missing: {path}; no automatic regeneration")
        if sha256(path) != config[key]:
            raise ValueError(f"Required historical artifact hash differs: {path}")
    _, bundle = load_bundle(predictor)
    _, frozen = load_checkpoint(checkpoint, bundle)
    return bundle, frozen


def group_schedule(config: dict, phase: str, group: int):
    phase_index = ("development", "final").index(phase)
    for pair in range(6):
        rotation = (group + pair) % 3
        arms = list(ARMS[rotation:] + ARMS[:rotation])
        targets = config["targets"] if group % 2 == 0 else config["targets"][::-1]
        for arm in arms:
            observer = digest(["v6-observer", phase, group, arm])[:24]
            for target in targets:
                session = digest(["v6-session", phase, group, arm, config["targets"].index(target)])[:24]
                yield {"group": group, "arm": arm, "target": target, "pair": pair,
                    "observer_key": observer, "session_key": session,
                    "seed": config["policy_seed_base"] + 100 * phase_index + 10 * group + pair,
                    "path": f"{phase}/g{group}/{arm}-p{pair}-vs-{target}"}


def validate_repair_config(config: dict):
    original = json.loads(CONFIG.read_text())
    allowed = {"schema_version", "seconds", "total_seconds", "overhead_seconds", "original_experiment"}
    if ({k: v for k, v in config.items() if k not in allowed} !=
        {k: v for k, v in original.items() if k not in allowed}
        or config["schema_version"] != "v6-acceptance-repair-1"
        or config["seconds"] != {"development": 420, "final": 1080}
        or config["total_seconds"] != 1800 or config["overhead_seconds"] != 300):
        raise ValueError("Replacement may change accounting/allocations only")
    reference = config["original_experiment"]
    for path, key in ((CONFIG, "config_sha256"), (SPEC, "spec_sha256"),
        (ROOT / reference["path"] / "artifact-hashes.json", "artifact_manifest_sha256"),
        (ROOT / "docs/MILESTONE6-FIRST-ATTEMPT.md", "historical_status_sha256")):
        if sha256(path) != reference[key]:
            raise ValueError("Original V6 evidence/specification changed")
    original_source = json.loads((ROOT / reference["path"] / "freeze.json").read_text())["source"]
    accounting_files = {f"src/battlemind/{name}.py" for name in
        ("adaptation_ledger", "adaptation_report", "adaptation_experiment", "cli")}
    if any(sha256(ROOT / path) != value for path, value in original_source.items() if path not in accounting_files):
        raise ValueError("Original scientific/runtime source changed")
    if config["memory"] != {"prior_encounters": PRIOR, "minimum_encounters": MIN_ENCOUNTERS,
        "minimum_examples": MIN_EXAMPLES, "maximum_adjustment": MAX_ADJUSTMENT, "probability_floor": FLOOR}:
        raise ValueError("Memory rules differ from the frozen configuration")


async def run_adaptation(output: Path) -> dict:
    config = json.loads(REPAIR_CONFIG.read_text())
    validate_repair_config(config)
    return await _run_specification(output, config, REPAIR_CONFIG, REPAIR_SPEC)


async def _run_specification(output: Path, config: dict, config_path: Path, spec_path: Path) -> dict:
    """Shared phase machinery; smaller specifications are injected only by tests."""
    started = time.monotonic()
    output = output.resolve()
    if output.exists():
        raise ValueError("V6 output must be fresh; resume/retry is unsupported")
    bundle, checkpoint = artifacts()
    output.mkdir(parents=True)
    ledger = AdaptationLedger(output, config, started=started)
    (output / "predictor.json").write_bytes(PREDICTOR.read_bytes())
    (output / "checkpoint.json").write_bytes(CHECKPOINT.read_bytes())
    freeze = {"version": "v6-freeze-2", "config": config, "config_sha256": sha256(config_path),
        "config_path": config_path.resolve().relative_to(ROOT).as_posix(),
        "spec_path": spec_path.resolve().relative_to(ROOT).as_posix(),
        "spec_sha256": sha256(spec_path), "source": source_manifest(), "predictor_sha256": bundle.sha256,
        "checkpoint_sha256": checkpoint.sha256, "parameters": asdict(checkpoint.parameters)}
    write_json(output / "freeze.json", freeze)

    def verify():
        if (source_manifest() != freeze["source"] or sha256(spec_path) != freeze["spec_sha256"]
            or sha256(config_path) != freeze["config_sha256"]):
            raise ValueError("Frozen V6 source/specification changed")
        artifacts(output / "predictor.json", output / "checkpoint.json")
        artifacts()

    failure = None
    try:
        for phase in ("development", "final"):
            if phase == "final":
                write_json(output / "final-freeze.json", {"freeze_sha256": sha256(output / "freeze.json"),
                    "development_run_ids": [r["run_id"] for r in ledger.state["runs"]],
                    "rules_changed_after_development": False, "final_memories_start_empty": True})
            ledger.begin(phase)
            for group in range(config["groups"][phase]):
                managers = {arm: ObserverMemory() for arm in ARMS}
                replay_managers = {arm: ObserverMemory() for arm in ARMS}
                ledger.state["resets"].append({"phase": phase, "group": group,
                    "observers": [digest(["v6-observer", phase, group, arm])[:24] for arm in ARMS], "all_empty": True})
                ledger.save()
                for cell in group_schedule(config, phase, group):
                    verify()
                    index = ledger.reserve(cell, config["cell_games"])
                    controller = EncounterController(managers[cell["arm"]], cell["session_key"], cell["observer_key"], cell["arm"], bundle)
                    run_config = RunConfig(agent_a="learned-score", agent_b=cell["target"], battles=4,
                        schedule_offset=4 * cell["pair"], teams=tuple(config["teams"]), seed=cell["seed"],
                        predictor=str(output / "predictor.json"), checkpoint_a=str(output / "checkpoint.json"),
                        turn_cap=config["turn_cap"], timeout=config["match_timeout"], run_timeout=min(600, ledger.remaining() - 10))
                    print(f"{cell['path']}: 4 games", flush=True)
                    ledger.dispatch(index)  # Reservation alone is not a request to execute games.
                    result = await run(run_config, output / cell["path"], start_server=True, memory_controller=controller)
                    battles = read_jsonl(output / cell["path"] / "battles.jsonl")
                    ledger.record(index, sha256(output / cell["path"] / "run.json"), battles, result)
                    if (result["completed"] != 4 or result["invalid_action_incidents"] or result["unexpected_client_warning_records"]
                        or result["server_crash_reports"]):
                        raise ValueError("Incomplete/invalid V6 cell; no retry or further memory use")
                    from .memory_audit import replay_cell
                    public_audit = replay_cell(output / cell["path"], replay_managers[cell["arm"]], bundle, checkpoint)
                    private_audit = audit_labels(output / cell["path"])
                    write_json(output / cell["path"] / "adaptation-audit.json", {"public_ok": public_audit["ok"],
                        "decisions": len(public_audit["decisions"]), "updates": public_audit["updates"], "commitment_audit": private_audit})
                    verify()
            ledger.finish_phase()
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        print(f"Stopped: {failure}", flush=True)
    finally:
        ledger.finish(failure)
    from .adaptation_report import build_adaptation_report
    try:
        deadline = min(ledger.started + config["total_seconds"], time.monotonic() + ledger.overhead_remaining()) - 5
        summary = build_adaptation_report(output, audit=True, write=True, deadline=deadline)
    except Exception as error:
        failure = failure or f"Report/audit: {type(error).__name__}: {error}"
        from .adaptation_report import outcome_metrics
        rows, unreadable = [], []
        for record in ledger.state["runs"]:
            try:
                rows.extend(read_jsonl(output / record["path"] / "battles.jsonl"))
            except (OSError, ValueError):
                unreadable.append(record["path"])
        summary = {"version": "v6-report-1", "audit_error": failure, "audit": {"ok": False},
            "outcomes": outcome_metrics(rows, ledger.state["requested_games"]),
            "unreadable_runs": unreadable, "phase_budgets": ledger.state["phases"]}
    hashes = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()}
    ledger.finalize(failure)  # Includes bulk hashing; tiny final manifest/ledger writes follow.
    summary.update(status=ledger.state["status"], failure=ledger.state["failure"],
        requested_games=ledger.state["requested_games"], consumed_seconds=ledger.state["consumed_seconds"],
        timing=ledger.state["timing"])
    write_json(output / "summary.json", summary)
    hashes.update({name: sha256(output / name) for name in ("ledger.json", "summary.json")})
    write_json(output / "artifact-hashes.json", hashes)
    return summary
