"""Pinned local server diagnostics and bounded lifecycle management."""

import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

import psutil
from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    bundle = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
    candidate = bundle / {"node": "node/bin/node.exe", "git": "native/git/cmd/git.exe"}[name]
    if candidate.is_file():
        return str(candidate)
    raise ValueError(f"{name} not found; install the version in configs/versions.json and add it to PATH")


def process_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(Path(executable("node")).parent) + os.pathsep + env.get("PATH", "")
    return env


def command(args: list[str], cwd: Path | None = None, stdin: str | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True,
                            encoding="utf-8", timeout=30, env=process_env())
    if result.returncode:
        raise ValueError(f"Command failed ({result.returncode}): {args}\n{result.stderr}\n{result.stdout}")
    return result.stdout.strip()


def inspect_server(showdown: Path, teams: list[Path], port: int) -> dict:
    from poke_env.data import GenData

    expected = json.loads((ROOT / "configs/versions.json").read_text())
    if not (showdown / "dist/sim/index.js").is_file():
        raise ValueError("Showdown is not built. Run scripts/setup-showdown.ps1")
    versions = {"python": platform.python_version(), "node": command([executable("node"), "--version"]),
                "poke_env": importlib.metadata.version("poke-env"),
                "showdown_commit": command([executable("git"), "rev-parse", "HEAD"], showdown),
                "showdown_version": json.loads((showdown / "package.json").read_text())["version"]}
    for key, value in versions.items():
        if value != expected[key]:
            raise ValueError(f"Version mismatch: {key}={value}; expected {expected[key]}")
    command([executable("git"), "diff", "--exit-code", "HEAD", "--", ".", ":(exclude)pnpm-lock.yaml"], showdown)
    if sha256(showdown / "config/config.js") != sha256(ROOT / "configs/showdown.config.js"):
        raise ValueError("Local server config differs from the reviewed loopback-only config")
    payload = {"format": "gen1ou", "teams": [{"path": str(p), "text": p.read_text()} for p in teams]}
    result = json.loads(command([executable("node"), str(ROOT / "scripts/inspect-server.cjs")], showdown, json.dumps(payload)))
    if not result["format"]["exists"] or result["format"]["mod"] != "gen1" or result["format"]["gameType"] != "singles":
        raise ValueError(f"Unsupported format: {result['format']}")
    for team in result["teams"]:
        if team["errors"]:
            raise ValueError(f"Illegal team {team['path']}: {team['errors']}")
        for mid, power in team["moves"].items():
            if GenData.from_gen(1).moves[mid]["basePower"] != power:
                raise ValueError(f"Gen 1 base-power mismatch between wrapper and engine: {mid}")
        for species, types in team["species_types"].items():
            if GenData.from_gen(1).pokedex[species]["types"] != types:
                raise ValueError(f"Gen 1 species type mismatch: {species}")
        for mid, rules in team["move_rules"].items():
            for key, value in rules.items():
                if key == "ignoreImmunity" and mid not in {"seismictoss", "nightshade"}:
                    continue  # only fixed-damage exceptions consume this field
                if GenData.from_gen(1).moves[mid].get(key) != value:
                    raise ValueError(f"Gen 1 move rule mismatch: {mid}.{key}")
    for defender, attacks in result["type_chart"].items():
        for attack, multiplier in attacks.items():
            if GenData.from_gen(1).type_chart[defender.upper()][attack.upper()] != multiplier:
                raise ValueError(f"Gen 1 type chart mismatch: {attack} -> {defender}")
    return {"versions": versions, "validation": result, "endpoint": f"ws://127.0.0.1:{port}/showdown/websocket",
            "teams": [{"path": str(p), "sha256": sha256(p)} for p in teams]}


async def healthcheck(port: int) -> dict:
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be 1024..65535")
    endpoint = f"ws://127.0.0.1:{port}/showdown/websocket"
    async with asyncio.timeout(5):
        async with connect(endpoint, open_timeout=3, proxy=None) as ws:
            for _ in range(10):
                message = str(await ws.recv())
                if "|challstr|" in message:
                    return {"ok": True, "endpoint": endpoint, "protocol": "Showdown challstr received"}
    raise ValueError("Server did not send a Showdown challenge string")


def stop_process_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for process in reversed(children):
            process.terminate()
        parent.terminate()
        _, alive = psutil.wait_procs(children + [parent], timeout=3)
        for process in alive:
            process.kill()
    except psutil.NoSuchProcess:
        pass


class LocalServer:
    def __init__(self, showdown: Path, port: int, log_path: Path, engine_log_dir: Path | None = None):
        self.showdown, self.port, self.log_path = showdown, port, log_path
        self.engine_log_dir = engine_log_dir or log_path.parent / "privileged/engine"
        self.process: subprocess.Popen | None = None
        self.log = None

    async def __aenter__(self):
        # Never take ownership of an existing listener.
        import socket
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", self.port)) == 0:
                raise ValueError(f"Port {self.port} already in use; use an unused port or an explicitly managed server")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open("x", encoding="utf-8")
        try:
            env = process_env()
            env["BATTLEMIND_LOG_DIR"] = str(self.engine_log_dir.resolve())
            Path(env["BATTLEMIND_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
            self.process = subprocess.Popen([executable("node"), "pokemon-showdown", "start", "--skip-build", str(self.port)],
                cwd=self.showdown, env=env, stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise ValueError(f"Showdown exited; see {self.log_path}")
                try:
                    await healthcheck(self.port)
                    if "CRASH:" in self.log_path.read_text(encoding="utf-8"):
                        raise ValueError(f"Showdown reported a startup error; see {self.log_path}")
                    return self
                except (OSError, TimeoutError):
                    await asyncio.sleep(0.2)
            raise TimeoutError(f"Showdown startup timeout; see {self.log_path}")
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *_):
        if self.process is not None:
            stop_process_tree(self.process.pid)
            self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def source_manifest() -> dict[str, str]:
    files = [ROOT / "pyproject.toml", ROOT / "requirements.lock"]
    files += list((ROOT / "src").rglob("*.py"))
    files += list((ROOT / "configs").rglob("*"))
    files += list((ROOT / "scripts").glob("*"))
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(files) if p.is_file()}
