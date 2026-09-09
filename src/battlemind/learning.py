"""The fixed V5 experiment: completed outcome updates, selection, then frozen play."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .dataset import write_json
from .environment import ROOT, sha256, source_manifest
from .labels import read_jsonl
from .learned_policy import PREDICTOR_SHA256, PolicyParameters, load_checkpoint, save_checkpoint
from .learning_ledger import ExperimentLedger
from .policy_search import complete_objective, outcome_update, propose, select_checkpoint
from .prediction_report import audit_predictions
from .runner import RunConfig, run
from .supervised_data import load_bundle

SPEC = ROOT / "docs/V5-EXPERIMENT.md"
CONFIG = ROOT / "configs/v5-experiment.json"


@dataclass(frozen=True, slots=True)
class Opponent:
    identity: str
    policy: str
    checkpoint: str | None = None
    checkpoint_sha256: str | None = None


def frozen_opponents(checkpoints: dict[str, Path], round_number: int) -> tuple[Opponent, ...]:
    if round_number not in {1, 2}:
        raise ValueError("Only the declared two training rounds are supported")
    names = ("c0",) if round_number == 1 else ("c0", "c1")
    return (Opponent("v2", "gen1-heuristic"), Opponent("active", "switch-active")) + tuple(
        Opponent(name, "learned-score", str(checkpoints[name]), sha256(checkpoints[name])) for name in names)


def verify_pool(pool: tuple[Opponent, ...]):
    if not isinstance(pool, tuple) or len(pool) > 6:
        raise ValueError("Opponent pool must be a bounded immutable tuple")
    for opponent in pool:
        if opponent.checkpoint and sha256(Path(opponent.checkpoint)) != opponent.checkpoint_sha256:
            raise ValueError("Frozen opponent changed inside a comparison")


async def train_experiment(output: Path, predictor: Path) -> dict:
    output, predictor = output.resolve(), predictor.resolve()
    if output.exists():
        raise ValueError("Experiment output must be fresh; resume/retry is unsupported")
    if sha256(predictor) != PREDICTOR_SHA256:
        raise ValueError("V5 requires the preserved original V4 predictor hash")
    _, bundle = load_bundle(predictor)
    configuration = json.loads(CONFIG.read_text())
    if (configuration["schema_version"] != "v5-experiment-1" or configuration["rounds"] != 2
        or configuration["cell_games"] != 24 or len(configuration["teams"]) != 4
        or configuration["phase_games"] != {"training": 336, "selection": 216, "final": 288}):
        raise ValueError("Unsupported V5 acceptance schedule; write a new specification for changes")
    output.mkdir(parents=True)
    ledger = ExperimentLedger(output, configuration)  # includes final reservation before c0 or training
    copied_predictor = output / "predictor.json"
    copied_predictor.write_bytes(predictor.read_bytes())
    frozen = {"schema_version": "v5-freeze-1", "configuration": configuration, "spec_sha256": sha256(SPEC),
        "configuration_sha256": sha256(CONFIG), "code_sha256": source_manifest(), "predictor_sha256": bundle.sha256,
        "rounds": 2, "selection_candidates": ["c0", "c1", "c2"],
        "final_opponents": ["random", "max", "v2", "active", "c0", "c1"], "resume_supported": False}
    write_json(output / "freeze.json", frozen)
    checkpoints = {"c0": output / "checkpoints/c0.json"}
    save_checkpoint(checkpoints["c0"], PolicyParameters(), bundle,
                    {"kind": "initialization", "freeze_sha256": sha256(output / "freeze.json")})
    updates, selection, failure = [], None, None

    def verify():
        if (source_manifest() != frozen["code_sha256"] or sha256(copied_predictor) != frozen["predictor_sha256"]
            or sha256(predictor) != frozen["predictor_sha256"] or sha256(SPEC) != frozen["spec_sha256"]):
            raise ValueError("Frozen source, specification or predictor changed")

    async def cell(name: str, candidate: Path, opponent: Opponent, seed: int, pool: tuple[Opponent, ...]) -> list[dict]:
        verify()
        verify_pool(pool)
        path = output / ledger.active / name
        candidate_hash = sha256(candidate)
        metadata = {"path": path.relative_to(output).as_posix(), "candidate": str(candidate.relative_to(output)),
            "candidate_sha256": candidate_hash, "opponent": asdict(opponent), "policy_seed": seed}
        index = ledger.reserve_run(configuration["cell_games"], metadata)
        config = RunConfig(agent_a="learned-score", agent_b=opponent.policy, battles=configuration["cell_games"],
            seed=seed, teams=tuple(configuration["teams"]), predictor=str(copied_predictor),
            checkpoint_a=str(candidate), checkpoint_b=opponent.checkpoint,
            turn_cap=configuration["turn_cap"], timeout=configuration["match_timeout"],
            run_timeout=min(600, ledger.remaining() - 15))
        print(f"{ledger.active}: {name}, 24 games", flush=True)
        result = await run(config, path, start_server=True)
        try:
            audit = audit_predictions(path)
        except Exception as error:
            audit = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        battles = read_jsonl(path / "battles.jsonl")
        ledger.finish_run(index, sha256(path / "run.json"), [b["match"] for b in battles], result, audit)
        if not audit["ok"]:
            raise ValueError("Run audit failed: " + audit["error"])
        verify()
        verify_pool(pool)
        if sha256(candidate) != candidate_hash:
            raise ValueError("Candidate changed during a completed batch")
        if result["unexpected_client_warning_records"] or result["invalid_action_incidents"] or result["server_crash_reports"]:
            raise ValueError("Action/warning incident; comparison is ineligible")
        complete_objective(battles, configuration["cell_games"])
        return battles

    try:
        ledger.begin("training")
        for number in (1, 2):
            parent_path = checkpoints[f"c{number - 1}"]
            _, parent = load_checkpoint(parent_path, bundle)
            proposal = propose(parent.parameters, configuration["proposal_seed_base"] + number)
            pool = frozen_opponents(checkpoints, number)
            round_path = output / f"rounds/round-{number}.json"
            round_record = {"number": number, "parent": str(parent_path.relative_to(output)),
                "parent_sha256": parent.sha256, "proposal": asdict(proposal), "opponents": [asdict(p) for p in pool]}
            write_json(round_path, round_record)  # proposal/pool frozen before any comparison game
            batches, sources = {}, {}
            for sign in ("plus", "minus"):
                candidate = output / f"checkpoints/round-{number}-{sign}.json"
                save_checkpoint(candidate, getattr(proposal, sign), bundle,
                    {"kind": "proposal", "round_sha256": sha256(round_path), "parent_sha256": parent.sha256, "sign": sign})
                batches[sign], sources[sign] = [], []
                for opponent in pool:
                    name = f"r{number}-{sign}-vs-{opponent.identity}"
                    batches[sign].extend(await cell(name, candidate, opponent, configuration["training_policy_seed_base"] + number, pool))
                    sources[sign].append(f"training/{name}")
            params, update = outcome_update(proposal, batches["plus"], batches["minus"], len(pool) * configuration["cell_games"])
            checkpoint = output / f"checkpoints/c{number}.json"
            update = {"round": number, "parent_sha256": parent.sha256, "proposal": asdict(proposal),
                "opponents": [asdict(p) for p in pool], "runs": sources, **update}
            save_checkpoint(checkpoint, params, bundle, {"kind": "outcome_update", **update})
            checkpoints[f"c{number}"] = checkpoint
            update["checkpoint"] = str(checkpoint.relative_to(output))
            update["checkpoint_sha256"] = sha256(checkpoint)
            write_json(output / f"rounds/update-{number}.json", update)
            updates.append(update)
            print(f"Update {number}: {params.values}, contrast={update['contrast']:.6f}", flush=True)
        ledger.finish_phase()
        ledger.begin("selection")
        c0 = checkpoints["c0"]
        pool = (Opponent("v2", "gen1-heuristic"), Opponent("moderate", "switch-moderate"),
                Opponent("c0", "learned-score", str(c0), sha256(c0)))
        entries, evidence = [], []
        for name in ("c0", "c1", "c2"):
            batch, sources = [], []
            _, checkpoint = load_checkpoint(checkpoints[name], bundle)
            for opponent in pool:
                cell_name = f"{name}-vs-{opponent.identity}"
                batch.extend(await cell(cell_name, checkpoints[name], opponent, configuration["selection_seed"], pool))
                sources.append(f"selection/{cell_name}")
            score = complete_objective(batch, len(pool) * configuration["cell_games"])
            entries.append((name, checkpoint.parameters, score))
            evidence.append({"checkpoint": name, "checkpoint_sha256": checkpoint.sha256,
                "parameters": asdict(checkpoint.parameters), "objective": score, "runs": sources})
        chosen = select_checkpoint(entries)
        selection = {"candidates": evidence, "chosen": chosen, "chosen_sha256": sha256(checkpoints[chosen]),
            "rule": "highest mean terminal reward, then smallest squared parameter norm, then earliest checkpoint"}
        write_json(output / "selection.json", selection)
        (output / "selected.json").write_bytes(checkpoints[chosen].read_bytes())
        ledger.finish_phase()
        c1 = checkpoints["c1"]
        pool = (Opponent("random", "random"), Opponent("max", "max-base-power"), Opponent("v2", "gen1-heuristic"),
            Opponent("active", "switch-active"), Opponent("c0", "learned-score", str(c0), sha256(c0)),
            Opponent("c1", "learned-score", str(c1), sha256(c1)))
        write_json(output / "final-freeze.json", {"selection_sha256": sha256(output / "selection.json"),
            "initial_sha256": sha256(c0), "selected_sha256": sha256(output / "selected.json"),
            "opponents": [asdict(p) for p in pool], "code_sha256": source_manifest(), "predictor_sha256": bundle.sha256})
        ledger.begin("final")
        for arm, checkpoint in (("initial", c0), ("selected", output / "selected.json")):
            for opponent in pool:
                await cell(f"{arm}-vs-{opponent.identity}", checkpoint, opponent, configuration["final_seed"], pool)
        ledger.finish_phase()
        verify()
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        print(f"Stopped: {failure}", flush=True)
    finally:
        ledger.finish(failure)
    from .learning_report import experiment_report, audit_experiment
    report = experiment_report(output, write_choices=True)
    if not failure:
        try:
            report["audit"] = audit_experiment(output)
        except Exception as error:
            failure = f"Postflight audit: {type(error).__name__}: {error}"
    ledger.finish(failure)  # includes offline reporting/audit time in aggregate accounting
    report["ledger_status"] = ledger.state["status"]
    report["failure"] = ledger.state["failure"]
    report["total_wall_seconds"] = ledger.state["consumed_wall_seconds"]
    write_json(output / "summary.json", report)
    write_json(output / "artifact-hashes.json", {p.relative_to(output).as_posix(): sha256(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return report
