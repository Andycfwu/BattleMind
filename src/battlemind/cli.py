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
    for name in ("doctor", "battle", "server"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", type=Path, default=ROOT / "configs/smoke.json")
        cmd.add_argument("--port", type=int)
        cmd.add_argument("--showdown")
        if name in {"doctor", "battle"}:
            cmd.add_argument("--start-server", action="store_true", help="Start and stop our pinned loopback server for this command")
        if name == "battle":
            for key, kind in (("agent-a", str), ("agent-b", str), ("battles", int), ("seed", int),
                              ("concurrency", int), ("turn-cap", int), ("timeout", float), ("run-timeout", float)):
                cmd.add_argument(f"--{key}", type=kind)
            cmd.add_argument("--output", type=Path)
        if name == "server":
            cmd.add_argument("--seconds", type=int, default=600, help="Stop automatically after this many seconds (max 3600)")
    cmd = sub.add_parser("report")
    cmd.add_argument("--run", type=Path, required=True)
    cmd.add_argument("--audit", action="store_true", help="Rebuild privileged labels and verify their evidence")
    return root


async def dispatch(args) -> tuple[dict, int]:
    if args.command == "report":
        result = report(args.run)
        if args.audit:
            from .labels import audit_labels
            result["audit"] = audit_labels(args.run)
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
