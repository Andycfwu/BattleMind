"""Local, sequential matches. The recorder is separate from each policy's inputs."""

import asyncio
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
from itertools import combinations
from pathlib import Path
import platform
import time
import uuid

from poke_env import AccountConfiguration, ServerConfiguration
from poke_env.battle import Battle
from poke_env.player import Player
from poke_env.player.battle_order import SingleBattleOrder
import psutil

from .adapter import PublicTracker, resolve_action, snapshot
from .environment import ROOT, LocalServer, healthcheck, inspect_server, source_manifest, sha256
from .labels import build_labels, engine_record, label_summary, read_jsonl, snapshot_hash
from .policies import POLICY_NAMES, make_policy
from .prediction import CountTable
from .supervised import PredictorBundle
from .learned_policy import FrozenCheckpoint, load_checkpoint
from .reporting import JsonlWriter, report
from .memory_runtime import EncounterController
from .opponent_memory import MemoryContext
from .schema import snapshot_from_dict


@dataclass(frozen=True)
class RunConfig:
    format: str = "gen1ou"
    agent_a: str = "random"
    agent_b: str = "max-base-power"
    battles: int = 2
    seed: int = 42
    concurrency: int = 1
    turn_cap: int = 300
    timeout: float = 60
    run_timeout: float = 600
    port: int = 8000
    showdown: str = ".local/pokemon-showdown"
    teams: tuple[str, ...] = ("configs/teams/ou-v1-a.txt", "configs/teams/ou-v1-b.txt")
    predictor: str | None = None
    checkpoint_a: str | None = None
    checkpoint_b: str | None = None
    schedule_offset: int = 0

    def validate(self) -> None:
        if self.format != "gen1ou":
            raise ValueError("Only the verified gen1ou format is supported")
        if self.concurrency != 1:
            raise ValueError("BattleMind supports concurrency=1 only")
        if type(self.schedule_offset) is not int or not 0 <= self.schedule_offset <= 100:
            raise ValueError("Schedule offset must be an integer in 0..100")
        if not 1 <= self.battles <= 100 or not 1 <= self.turn_cap <= 1000:
            raise ValueError("Use 1..100 battles and 1..1000 turns")
        if not 0.01 <= self.timeout <= 300 or not 0.01 <= self.run_timeout <= 3600:
            raise ValueError("Timeouts must be positive and bounded (match <=300s, run <=3600s)")
        if not 1024 <= self.port <= 65535 or not self.teams:
            raise ValueError("Use a port in 1024..65535 and at least one team")
        for agent, checkpoint in ((self.agent_a, self.checkpoint_a), (self.agent_b, self.checkpoint_b)):
            if agent not in POLICY_NAMES:
                raise ValueError(f"Unknown policy: {agent}")
            if agent in {"switch-constant", "switch-context", "switch-logistic", "learned-score"} and not self.predictor:
                raise ValueError("Switch-aware policies require --predictor")
            if (agent == "learned-score") != (checkpoint is not None):
                raise ValueError("Each learned-score side requires its own checkpoint; other policies take no checkpoint")


def policy_seed(seed: int, match: int, side: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{match}:{side}".encode()).digest()[:8], "big")


def scheduled_match(index: int, team_count: int) -> tuple[dict[str, int], str]:
    """Four-game blocks: both assignments on both challenger sides for each pair."""
    pairs = list(combinations(range(team_count), 2)) or [(0, 0)]
    pair = pairs[(index // 4) % len(pairs)]
    a, b = pair if index % 2 == 0 else pair[::-1]
    return {"a": a, "b": b}, "a" if index % 4 < 2 else "b"


@dataclass
class MatchState:
    index: int
    turn_cap: int
    decisions_log: JsonlWriter
    events_log: JsonlWriter
    reason: str | None = None
    detail: str | None = None
    invalid_actions: int = 0
    decisions: int = 0
    turns: int = 0
    tags: set[str] = field(default_factory=set)
    results: dict[str, str] = field(default_factory=dict)

    def fail(self, reason: str, detail: str) -> None:
        if self.reason is None:
            self.reason, self.detail = reason, detail


class ErrorRecorder(logging.Handler):
    def __init__(self, state: MatchState, side: str):
        super().__init__(logging.WARNING)
        self.state, self.side = state, side

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        # Messages remain recorder-only. No log or recorder object enters a policy.
        self.state.events_log.write({"match": self.state.index, "player": self.side,
                                    "kind": "client_log", "level": record.levelname, "message": message})
        if record.levelno >= logging.ERROR or "Popup message" in message:
            self.state.fail("crash", message[:1000])


class LocalPlayer(Player):
    def __init__(self, *, policy_name: str, seed: int, side: str, state: MatchState,
                 journal: JsonlWriter | None = None, counts: CountTable | PredictorBundle | None = None,
                 checkpoint: FrozenCheckpoint | None = None, memory_context: MemoryContext | None = None,
                 memory_mode: str | None = None, **kwargs):
        self.policy = make_policy(policy_name, seed, counts, checkpoint)
        if memory_context is not None:
            from .adaptation import AdaptedAgent
            if policy_name != "learned-score":
                raise ValueError("V6 uses frozen learned-score only")
            self.policy = AdaptedAgent(counts, checkpoint, memory_context, memory_mode)
        self.side, self.state = side, state
        self.journal = journal or state.decisions_log
        self.trackers: dict[str, PublicTracker] = {}
        self.request_ids: dict[str, int] = {}
        super().__init__(**kwargs)

    async def _handle_battle_message(self, split_messages):
        """Pinned poke-env hook: consume lines in order so batched future events cannot leak."""
        header = split_messages[0]
        tag = header[0].lstrip(">")
        self.state.tags.add(tag)
        tracker = self.trackers.setdefault(tag, PublicTracker())
        try:
            for line in split_messages[1:]:
                if len(line) > 3 and line[1] == "player" and line[3] == self.username:
                    tracker.role = line[2]
                if len(line) > 2 and line[1] == "request" and line[2]:
                    parsed = json.loads(line[2])
                    if parsed is None:
                        continue
                    tracker.request(parsed)
                if len(line) > 1 and line[1] in {"error", "bigerror"}:
                    text = "|".join(line[2:])
                    self.state.invalid_actions += int("choice" in text.lower())
                    self.state.events_log.write({"match": self.state.index, "player": self.side,
                                                "kind": "server_error", "message": text})
                    self.state.fail("crash", text)
                    # Do not allow poke-env's probabilistic silent default/retry.
                    continue
                tracker.feed(line)
                await super()._handle_battle_message([header, line])
        except Exception as exc:
            self.state.fail("crash", f"{type(exc).__name__}: {exc}")
            self.state.events_log.write({"match": self.state.index, "player": self.side,
                                        "kind": "adapter_exception", "message": repr(exc)})

    async def _handle_battle_request(self, battle, maybe_default_order=False):
        # Override only the request dispatch: no team preview or implicit default in Gen 1.
        if battle.last_request.get("wait") or self.state.reason:
            return
        if maybe_default_order:
            self.state.fail("crash", "Unexpected library retry")
            return
        self.state.turns = max(self.state.turns, battle.turn)
        if battle.turn > self.state.turn_cap:
            self.state.fail("truncated", f"Turn cap {self.state.turn_cap} reached")
            return
        rqid = battle.last_request["rqid"]
        if self.request_ids.get(battle.battle_tag) == rqid:
            return
        self.request_ids[battle.battle_tag] = rqid
        order = self.choose_move(battle)
        await self.ps_client.send_message(order.message, battle.battle_tag)
        self.state.events_log.write({"match": self.state.index, "player": self.side,
                                    "kind": "submitted", "request_id": rqid})

    def choose_move(self, battle: Battle) -> SingleBattleOrder:
        observation, mapping = snapshot(battle, self.trackers[battle.battle_tag])
        evaluation = self.policy.evaluate(observation) if hasattr(self.policy, "evaluate") else None
        chosen = evaluation.chosen_action if evaluation else self.policy.choose(observation)
        command = resolve_action(chosen, observation, mapping)
        data = asdict(observation)
        scores = evaluation.scores if evaluation else self.policy.scores(observation) if hasattr(self.policy, "scores") else ()
        self.journal.write({"schema_version": "3.0" if evaluation else "2.0", "match": self.state.index,
            "decision_id": f"m{self.state.index}:{self.side}:r{observation.request_id}",
            "snapshot_sha256": snapshot_hash(data),
            "player": self.side, "observation": data, "legal_mapping": mapping,
            "chosen_action": chosen, "command": command, "action_scores": [asdict(s) for s in scores],
            **({"prediction_evaluation": asdict(evaluation)} if evaluation else {}),
            "action_semantics": "local intention; commitment and execution require separate evidence"})
        self.state.decisions += 1
        return SingleBattleOrder(command)

    def _battle_finished_callback(self, battle):
        result = "win" if battle.won else "loss" if battle.lost else "draw"
        self.state.results[self.side] = result
        self.state.turns = max(self.state.turns, battle.turn)
        self.state.events_log.write({"match": self.state.index, "player": self.side,
                                    "kind": "terminal", "result": result, "turn": battle.turn})


async def close_players(players: list[LocalPlayer]) -> None:
    for player in players:
        for battle in player.battles.values():
            if not battle.finished:
                try:
                    await asyncio.wait_for(player.ps_client.send_message("/forfeit", battle.battle_tag), 2)
                except (OSError, TimeoutError):
                    pass
    for player in players:
        if hasattr(player.ps_client, "websocket"):
            await asyncio.wait_for(player.ps_client.stop_listening(), 3)
        player.ps_client._listening_coroutine.cancel()
        tasks = list(player.ps_client._active_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def play_match(config: RunConfig, index: int, decisions: JsonlWriter, events: JsonlWriter,
                     deadline: float, output: Path, engine_logs: Path, labels_log: JsonlWriter,
                     counts: CountTable | PredictorBundle | None = None,
                     checkpoints: dict[str, FrozenCheckpoint] | None = None,
                     memory_controller: EncounterController | None = None) -> dict:
    state = MatchState(index, config.turn_cap, decisions, events)
    start = time.monotonic()
    assignments, challenger = scheduled_match(index + config.schedule_offset, len(config.teams))
    seeds = {s: policy_seed(config.seed, index, s) for s in ("a", "b")}
    players: list[LocalPlayer] = []
    handlers: list[ErrorRecorder] = []
    battle_task = None
    journals = {s: JsonlWriter(output / "privileged/attempts" / f"{index:03d}-{s}.jsonl") for s in ("a", "b")}
    try:
        memory_context = memory_controller.before(output, index) if memory_controller else None
        for side, name in (("a", config.agent_a), ("b", config.agent_b)):
            player = LocalPlayer(policy_name=name, seed=seeds[side], side=side, state=state,
                journal=journals[side], counts=counts, checkpoint=(checkpoints or {}).get(side),
                memory_context=memory_context if side == "a" else None,
                memory_mode=memory_controller.mode if memory_controller and side == "a" else None,
                account_configuration=AccountConfiguration("bm" + uuid.uuid4().hex[:16], None),
                server_configuration=ServerConfiguration(f"ws://127.0.0.1:{config.port}/showdown/websocket", "http://127.0.0.1:1/action.php?"),
                battle_format=config.format, max_concurrent_battles=1, open_timeout=5,
                loop=asyncio.get_running_loop(), log_level=logging.WARNING,
                team=(ROOT / config.teams[assignments[side]]).read_text())
            handler = ErrorRecorder(state, side)
            player.logger.addHandler(handler)
            handlers.append(handler)
            players.append(player)
        first, second = players if challenger == "a" else players[::-1]
        battle_task = asyncio.create_task(first.battle_against(second, n_battles=1))
        end = min(start + config.timeout, deadline)
        while not battle_task.done() and not state.reason:
            if time.monotonic() >= end:
                state.fail("timeout", "Run deadline" if end == deadline else "Match timeout")
                break
            await asyncio.sleep(0.01)
        if battle_task.done():
            await battle_task
        if not state.reason and state.results not in ({"a": "win", "b": "loss"}, {"a": "loss", "b": "win"}, {"a": "draw", "b": "draw"}):
            state.fail("crash", f"Missing or inconsistent terminal results: {state.results}")
    except asyncio.CancelledError:
        state.fail("cancelled", "Run interrupted")
    except Exception as exc:
        state.fail("crash", f"{type(exc).__name__}: {exc}")
    finally:
        if battle_task:
            battle_task.cancel()
            await asyncio.gather(battle_task, return_exceptions=True)
        try:
            await close_players(players)
        except Exception as exc:
            state.fail("crash", f"Cleanup error: {exc}")
        for player, handler in zip(players, handlers):
            player.logger.removeHandler(handler)
            for remaining in list(player.logger.handlers):
                player.logger.removeHandler(remaining)
                remaining.close()
        for journal in journals.values():
            journal.close()
    if memory_controller and memory_controller.pending is not None:
        try:
            # Read only observer a's own journal and its own public tracker, before any privileged join.
            observer = next((p for p in players if p.side == "a"), None)
            observations = tuple(snapshot_from_dict(r["observation"]) for r in
                read_jsonl(output / "privileged/attempts" / f"{index:03d}-a.jsonl"))
            history = tuple(e for tracker in observer.trackers.values() for e in tracker.history) if observer else ()
            memory_controller.after(output, index, observations, history, state.reason is None)
        except Exception as exc:
            state.fail("crash", f"Observer memory error: {exc}")
    # Both clients are now stopped. Only this post-match recorder reads both attempts.
    rows = sorted([r for s in ("a", "b") for r in read_jsonl(output / "privileged/attempts" / f"{index:03d}-{s}.jsonl")],
                  key=lambda r: r["observation"]["request_id"])
    for row in rows:
        decisions.write(row)
    histories = json.loads(json.dumps({p.side: [asdict(e) for tracker in p.trackers.values() for e in tracker.history] for p in players}))
    roles = {p.side: tracker.role for p in players for tracker in p.trackers.values()}
    (output / "privileged" / f"{index:03d}-histories.json").write_text(json.dumps(histories))
    raw, raw_path, label_error = await engine_record(engine_logs, state.tags, {p.username for p in players})
    evidence = None
    if raw_path:
        # Manual servers write outside the run; retain a byte-for-byte recorder copy.
        if not raw_path.resolve().is_relative_to(output.resolve()):
            copy_path = output / "privileged" / f"{index:03d}-engine.json"
            copy_path.write_bytes(raw_path.read_bytes())
            raw_path = copy_path
        evidence = {"path": raw_path.relative_to(output).as_posix(), "sha256": sha256(raw_path)}
    labels = build_labels(rows, histories, raw, roles, state.reason or "completed", label_error)
    for label in labels:
        labels_log.write(label)
    winner = None if state.reason else "a" if state.results.get("a") == "win" else "b" if state.results.get("b") == "win" else "draw"
    return {"schema_version": "2.0", "match": index, "status": state.reason or "completed", "winner": winner,
            "detail": state.detail, "terminal_results": state.results, "battle_tags": sorted(state.tags),
            "turns": state.turns, "seconds": time.monotonic() - start, "decisions": state.decisions,
            "invalid_actions": state.invalid_actions, "team_indices": assignments, "challenger": challenger,
            "policy_seeds": seeds, "engine_record": evidence, "player_roles": roles,
            "labels": label_summary(labels)}


async def run(config: RunConfig, output: Path, start_server: bool = False,
              memory_controller: EncounterController | None = None) -> dict:
    config.validate()
    if memory_controller and config.agent_a != "learned-score":
        raise ValueError("Observer memory requires frozen learned-score player a")
    diagnostics = inspect_server((ROOT / config.showdown).resolve(), [ROOT / p for p in config.teams], config.port)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "privileged/attempts").mkdir(parents=True)
    counts, predictor_meta = None, None
    if config.predictor:
        from .dataset import load_predictor
        # Freeze once; policies get fitted parameters/digest, never offline provenance IDs.
        source = ROOT / config.predictor
        (output / "predictor.json").write_bytes(source.read_bytes())
        _, counts = load_predictor(output / "predictor.json")
        predictor_meta = {"source_path": str(source.resolve()), "sha256": sha256(output / "predictor.json"),
                          "evaluation_updates": False}
    checkpoints, checkpoint_meta = {}, {}
    for side, path in (("a", config.checkpoint_a), ("b", config.checkpoint_b)):
        if path is not None:
            if not isinstance(counts, PredictorBundle):
                raise ValueError("Learned checkpoints require a compatible supervised predictor")
            destination = output / f"checkpoint-{side}.json"
            destination.write_bytes((ROOT / path).read_bytes())
            _, checkpoints[side] = load_checkpoint(destination, counts)
            checkpoint_meta[side] = {"path": destination.name, "sha256": sha256(destination), "evaluation_updates": False}
    metadata = {"schema_version": "2.0", "created_utc": datetime.now(timezone.utc).isoformat(),
                "config": asdict(config), "environment": diagnostics, "code_sha256": source_manifest(),
                "predictor": predictor_meta,
                **({"adaptation": memory_controller.metadata()} if memory_controller else {}),
                **({"policy_checkpoints": checkpoint_meta} if checkpoint_meta else {}),
                "policies": {"a": {"name": config.agent_a, "version": make_policy(config.agent_a, config.seed, counts, checkpoints.get("a")).version},
                             "b": {"name": config.agent_b, "version": make_policy(config.agent_b, config.seed, counts, checkpoints.get("b")).version}},
                "host": {"os": platform.platform(), "logical_cpus": psutil.cpu_count(),
                         "ram_bytes": psutil.virtual_memory().total},
                "randomness": {"policy": "SHA256(root seed:match index:a/b), independent random.Random",
                               "teams": "balanced-v2: all unordered pairs; four games per pair, swapped assignments and challenger",
                               "simulator_seed": None, "exact_replay_determinism": False}}
    (output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    decisions, battles, events = [JsonlWriter(output / f"{name}.jsonl") for name in ("decisions", "battles", "events")]
    labels_log = JsonlWriter(output / "privileged/labels.jsonl")
    started, cpu_start = time.monotonic(), time.process_time()
    peak_rss = 0
    peak_server_rss = 0
    server_cpu_seconds = None
    stop_sampling = asyncio.Event()
    server_pid: int | None = None

    async def sample():
        nonlocal peak_rss, peak_server_rss, server_cpu_seconds
        while not stop_sampling.is_set():
            peak_rss = max(peak_rss, psutil.Process().memory_info().rss)
            if server_pid is not None:
                try:
                    parent = psutil.Process(server_pid)
                    group = [parent] + parent.children(recursive=True)
                    peak_server_rss = max(peak_server_rss, sum(p.memory_info().rss for p in group))
                    server_cpu_seconds = sum(sum(p.cpu_times()[:2]) for p in group)
                except psutil.NoSuchProcess:
                    pass
            await asyncio.sleep(0.1)

    sampler = asyncio.create_task(sample())
    recorded = 0
    abort_reason = None
    try:
        async with AsyncExitStack() as stack:
            if start_server:
                server = await stack.enter_async_context(LocalServer(ROOT / config.showdown, config.port, output / "server.log"))
                server_pid = server.process.pid
            await healthcheck(config.port)
            deadline = started + config.run_timeout
            for index in range(config.battles):
                if time.monotonic() >= deadline:
                    abort_reason = "Run deadline reached"
                    break
                log_root = output / "privileged/engine" if start_server else ROOT / config.showdown / "logs"
                row = await play_match(config, index, decisions, events, deadline, output, log_root, labels_log, counts, checkpoints, memory_controller)
                battles.write(row)
                recorded += 1
                print(f"Match {index + 1}/{config.battles}: {row['status']} winner={row['winner']} turns={row['turns']}", flush=True)
                if row["status"] in {"crash", "cancelled", "timeout"}:
                    abort_reason = row["detail"]
                    break
    except asyncio.CancelledError:
        abort_reason = "Run interrupted"
    except Exception as exc:
        abort_reason = f"{type(exc).__name__}: {exc}"
        events.write({"kind": "run_error", "message": abort_reason})
    finally:
        for index in range(recorded, config.battles):
            battles.write({"match": index, "status": "not_started", "winner": None, "detail": abort_reason})
        stop_sampling.set()
        await sampler
        for writer in (decisions, battles, events, labels_log):
            writer.close()
        resources = {"wall_seconds": time.monotonic() - started, "python_cpu_seconds": time.process_time() - cpu_start,
                     "python_peak_sampled_rss_bytes": peak_rss, "managed_server_peak_sampled_rss_bytes": peak_server_rss if start_server else None,
                     "managed_server_cpu_seconds_last_sample": server_cpu_seconds,
                     "sampling_seconds": 0.1, "external_server_resources": "not measured" if not start_server else "managed locally"}
        (output / "resources.json").write_text(json.dumps(resources, indent=2) + "\n")
    summary = report(output)
    summary["run_directory"] = str(output)
    return summary
