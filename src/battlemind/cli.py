import argparse
import asyncio
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path

from .environment import ROOT, LocalServer, healthcheck, inspect_server
from .reporting import report
from .runner import RunConfig, run


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="BattleMind: bounded local gen1ou baseline experiments")
    sub = root.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser('actor-step-run', help='One frozen controlled actor-step experiment; no resume')
    cmd.add_argument('--spec', type=Path, required=True)
    cmd.add_argument('--output', type=Path, required=True)
    cmd = sub.add_parser('actor-step-report', help='Read-only controlled actor-step outcomes and update replay')
    cmd.add_argument('--experiment', type=Path, required=True)
    cmd.add_argument('--audit', action='store_true')
    cmd = sub.add_parser('reinforce-run', help='Single-use bounded research extension: smoke or frozen main specification')
    cmd.add_argument('--spec', type=Path, required=True)
    cmd.add_argument('--output', type=Path, required=True)
    cmd = sub.add_parser('reinforce-report', help='Read-only outcome, policy-gradient update and partition audit')
    cmd.add_argument('--experiment', type=Path, required=True)
    cmd.add_argument('--audit', action='store_true')
    cmd = sub.add_parser('evidence', help='Read-only consolidation of retained V1-V6 evidence')
    cmd.add_argument('--output', type=Path, required=True)
    cmd = sub.add_parser('demo-prepare', help='Package preselected retained public examples and compatible artifacts')
    cmd.add_argument('--output', type=Path, required=True)
    for name in ('bundle-export','bundle-import'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--source', type=Path, required=True)
        cmd.add_argument('--output', type=Path, required=True)
    cmd = sub.add_parser('bundle-verify')
    cmd.add_argument('--bundle', type=Path, required=True)
    cmd = sub.add_parser('demo-serve', help='Local viewer; independent bounded functional games only')
    cmd.add_argument('--bundle', type=Path, required=True)
    cmd.add_argument('--output', type=Path, required=True)
    cmd.add_argument('--port', type=int, default=8765)
    cmd.add_argument('--games', type=int, default=2)
    cmd.add_argument('--seconds', type=int, default=1800)
    cmd.add_argument('--recordings', type=Path, help='Finished public replay exports only; never raw/private logs')
    cmd.add_argument('--reinforce-checkpoint', type=Path, help='Optional compatible frozen research policy; historical defaults unchanged')
    for name in ("doctor", "battle", "server"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", type=Path, default=ROOT / "configs/smoke.json")
        cmd.add_argument("--port", type=int)
        cmd.add_argument("--showdown")
        if name in {"doctor", "battle"}:
            cmd.add_argument("--start-server", action="store_true", help="Start and stop our pinned loopback server for this command")
        if name == "battle":
            cmd.add_argument("--predictor", help="Frozen local counts or supervised JSON bundle; copied into the run")
            cmd.add_argument("--checkpoint-a", help="Frozen learned-score checkpoint for player a")
            cmd.add_argument("--checkpoint-b", help="Frozen learned-score checkpoint for player b")
            for key, kind in (("agent-a", str), ("agent-b", str), ("battles", int), ("seed", int),
                              ("concurrency", int), ("turn-cap", int), ("timeout", float), ("run-timeout", float)):
                cmd.add_argument(f"--{key}", type=kind)
            cmd.add_argument("--output", type=Path)
        if name == "server":
            cmd.add_argument("--seconds", type=int, default=600, help="Stop automatically after this many seconds (max 3600)")
    cmd = sub.add_parser("report")
    cmd.add_argument("--run", type=Path, required=True)
    cmd.add_argument("--audit", action="store_true", help="Rebuild privileged labels and verify their evidence")
    cmd = sub.add_parser("dataset", help="Build audited observer features and whole-battle partitions")
    cmd.add_argument("--runs", nargs="+", type=Path, required=True)
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--seed", type=int, default=2026)
    cmd.add_argument("--role", choices=("development", "evaluation"), default="development")
    cmd = sub.add_parser("predictor-fit", help="Estimate and freeze smoothed counts from development_fit only")
    cmd.add_argument("--dataset", type=Path, required=True)
    cmd.add_argument("--output", type=Path, required=True)
    cmd = sub.add_parser("predictor-evaluate", help="Compare frozen probabilities on audited labels")
    cmd.add_argument("--dataset", type=Path, required=True)
    cmd.add_argument("--predictor", type=Path, required=True)
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--partition", choices=("development_check", "evaluation"), required=True)
    cmd.add_argument("--target-policies", nargs="+")
    cmd = sub.add_parser("supervised-dataset", help="Audited local records to V4 visible features")
    cmd.add_argument("--runs", nargs="+", type=Path, required=True)
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--seed", type=int, default=20260909)
    cmd.add_argument("--role", choices=("development", "evaluation"), default="development")
    for name in ("supervised-train", "supervised-evaluate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--dataset", type=Path, required=True)
        cmd.add_argument("--output", type=Path, required=True)
        if name == "supervised-evaluate":
            cmd.add_argument("--predictor", type=Path, required=True)
            cmd.add_argument("--partition", choices=("development_check", "evaluation"), required=True)
    cmd = sub.add_parser("policy-train", help="Run the fixed bounded V5 training, selection and reserved final experiment")
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--predictor", type=Path, default=ROOT / "models/v4-supervised.json")
    cmd = sub.add_parser("policy-evaluate", help="Evaluate one frozen checkpoint locally; no updates")
    cmd.add_argument("--checkpoint", type=Path, required=True)
    cmd.add_argument("--predictor", type=Path, default=ROOT / "models/v4-supervised.json")
    cmd.add_argument("--opponent", default="gen1-heuristic")
    cmd.add_argument("--opponent-checkpoint", type=Path)
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--battles", type=int, default=24)
    cmd.add_argument("--seed", type=int, default=51801)
    cmd = sub.add_parser("policy-report", help="Read or fully audit a retained learning experiment; no games/updates")
    cmd.add_argument("--experiment", type=Path, required=True)
    cmd.add_argument("--audit", action="store_true")
    cmd = sub.add_parser("adaptation-run", help="The separately authorized single-use V6 acceptance repair")
    cmd.add_argument("--specification", choices=("repair",), required=True,
        help="Explicit replacement specification; the original consumed experiment cannot resume")
    cmd.add_argument("--output", type=Path, required=True)
    cmd = sub.add_parser("adaptation-report", help="Read or replay-audit a V6 experiment; no games")
    cmd.add_argument("--experiment", type=Path, required=True)
    cmd.add_argument("--audit", action="store_true")
    return root


async def dispatch(args) -> tuple[dict, int]:
    if args.command == 'actor-step-run':
        from .actor_step_experiment import experiment
        result=await experiment(args.spec,args.output)
        return result, 0 if result['status']=='finished' else 1
    if args.command == 'actor-step-report':
        from .actor_step_experiment import report_experiment
        result=report_experiment(args.experiment,args.audit)
        return result, 0 if result['audit']['ok'] else 1
    if args.command == 'reinforce-run':
        from .reinforce_experiment import experiment
        result=await experiment(args.spec,args.output)
        return result, 0 if result['status']=='finished' else 1
    if args.command == 'reinforce-report':
        from .reinforce_experiment import report_experiment
        result=report_experiment(args.experiment,args.audit)
        return result, 0 if result['audit']['ok'] else 1
    if args.command == 'evidence':
        from .evidence import build_catalog
        result = build_catalog(args.output)
        return result, 0 if result['ok'] else 1
    if args.command in {'demo-prepare','bundle-export','bundle-import','bundle-verify'}:
        from .demo_bundle import prepare, export_bundle, import_bundle, verify
        if args.command == 'demo-prepare': result = prepare(args.output)
        elif args.command == 'bundle-export': result = export_bundle(args.source,args.output)
        elif args.command == 'bundle-import': result = import_bundle(args.source,args.output)
        else: result = verify(args.bundle)
        return result, 0
    if args.command == 'demo-serve':
        from .demo_server import serve
        return await serve(args.bundle,args.output,args.port,args.games,args.seconds,args.recordings,args.reinforce_checkpoint), 0
    if args.command == "adaptation-run":
        from .adaptation_experiment import run_adaptation
        result = await run_adaptation(args.output)
        return result, 0 if result["status"] == "finished" else 1
    if args.command == "adaptation-report":
        from .adaptation_report import build_adaptation_report
        result = (build_adaptation_report(args.experiment, audit=True) if args.audit else
                  json.loads((args.experiment / "summary.json").read_text()))
        return result, 0 if result["status"] == "finished" else 1
    if args.command == "policy-train":
        from .learning import train_experiment
        result = await train_experiment(args.output, args.predictor)
        return result, 0 if result["ledger_status"] == "finished" else 1
    if args.command == "policy-evaluate":
        from .prediction_report import audit_predictions
        teams = tuple(json.loads((ROOT / "configs/v5-experiment.json").read_text())["teams"])
        config = RunConfig(agent_a="learned-score", agent_b=args.opponent, teams=teams,
            battles=args.battles, seed=args.seed, predictor=str(args.predictor), checkpoint_a=str(args.checkpoint),
            checkpoint_b=str(args.opponent_checkpoint) if args.opponent_checkpoint else None)
        result = await run(config, args.output, start_server=True)
        result["audit"] = audit_predictions(args.output)
        return result, 0 if result["completed"] == args.battles and not result["invalid_action_incidents"] else 1
    if args.command == "policy-report":
        from .learning_report import audit_experiment
        result = json.loads((args.experiment / "summary.json").read_text())
        if args.audit:
            result["audit"] = audit_experiment(args.experiment)
        return result, 0 if result["ledger_status"] == "finished" else 1
    if args.command == "supervised-dataset":
        from .supervised_data import build_supervised_dataset
        result = build_supervised_dataset(args.runs, args.output, args.seed, args.role)
        return {"output": str(args.output), "balance": result["primary_balance"], "exclusions": result["exclusions"]}, 0
    if args.command == "supervised-train":
        from .supervised_training import train_bundle
        result = train_bundle(args.dataset, args.output)
        return {"output": str(args.output), "fit_balance": result["fit_balance"], "validation_balance": result["validation_balance"],
                "selection": result["selection"], "resources": result["resources"]}, 0
    if args.command == "supervised-evaluate":
        from .supervised_report import evaluate_bundle
        result = evaluate_bundle(args.dataset, args.predictor, args.output, args.partition)
        return {"output": str(args.output), "balance": result["balance"], "metrics": result["metrics"],
                "paired_battle_bootstrap": result["paired_battle_bootstrap"]}, 0
    if args.command == "dataset":
        from .dataset import build_dataset
        result = build_dataset(args.runs, args.output, args.seed, args.role)
        return {"output": str(args.output), "balance": result["balance"], "exclusions": result["exclusions"]}, 0
    if args.command == "predictor-fit":
        from .dataset import fit_predictor
        result = fit_predictor(args.dataset, args.output)
        return {"output": str(args.output), "fit_balance": result["fit_balance"], "table": result["table"]}, 0
    if args.command == "predictor-evaluate":
        from .prediction_report import evaluate_predictor
        result = evaluate_predictor(args.dataset, args.predictor, args.output, args.partition, args.target_policies)
        return {"output": str(args.output), "balance": result["balance"], "metrics": result["metrics"],
                "paired_battle_bootstrap": result["paired_battle_bootstrap"]}, 0
    if args.command == "report":
        result = report(args.run)
        if args.audit:
            from .prediction_report import audit_predictions
            result["audit"] = audit_predictions(args.run)
        return result, 0
    data = json.loads(args.config.read_text())
    for field in fields(RunConfig):
        value = getattr(args, field.name, None)
        if value is not None:
            data[field.name] = value
    data["teams"] = tuple(data.get("teams", RunConfig().teams))
    config = RunConfig(**data)
    config.validate()
    if args.command == "battle":
        output = args.output or ROOT / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        result = await run(config, output, args.start_server)
        return result, 0 if result["completed"] == config.battles and not result["invalid_action_incidents"] else 1
    result = inspect_server(ROOT / config.showdown, [ROOT / p for p in config.teams], config.port)
    if args.command == "server" or args.start_server:
        if args.command == "server" and not 1 <= args.seconds <= 3600:
            raise ValueError("Server duration must be 1..3600 seconds")
        log = ROOT / ".local" / ("server-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + ".log")
        # A separately launched server uses the same location the external-run recorder reads.
        engine_logs = ROOT / config.showdown / "logs" if args.command == "server" else None
        async with LocalServer(ROOT / config.showdown, config.port, log, engine_logs):
            result["connection"] = await healthcheck(config.port)
            if args.command == "server":
                print(f"Listening only on 127.0.0.1:{config.port}; Ctrl+C stops the server. Log: {log}", flush=True)
                await asyncio.sleep(args.seconds)
    else:
        result["connection"] = await healthcheck(config.port)
    return result, 0


def main() -> int:
    args = parser().parse_args()
    try:
        result, code = asyncio.run(dispatch(args))
        print(json.dumps(result, indent=2))
        return code
    except KeyboardInterrupt:
        print("Interrupted; managed server stopped.")
        return 130
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1
