#!/usr/bin/env python3
"""Readable local engine helpers for the ts-bench matrix runner.

The original benchmark-engine-matrix.py can become a dataless iCloud
FileProvider file on this machine. Keep this small helper readable so long
bench runs do not block while the source file is being materialized.
"""

from __future__ import annotations

from contextlib import contextmanager, suppress
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any


ROOT = Path(__file__).resolve().parent
DRAFT_REF = "z-lab/Qwen3.6-35B-A3B-DFlash"
BACKEND_ENV = ROOT / ".dflash-backend.env"
RELEASE_GATEWAY = ROOT / "_release" / "qwen36-dflash-ddtree-gateway" / "dflash_gateway.py"


@dataclass(frozen=True)
class Candidate:
    name: str
    target: str
    draft: str = DRAFT_REF


def load_candidates() -> list[Candidate]:
    return [
        Candidate("qwen36_35b_a3b_thecluster", "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit"),
        Candidate(
            "qwen36_35b_a3b_youssofal",
            "Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit",
        ),
        Candidate(
            "qwen36_35b_a3b_froggeric",
            "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
        ),
        Candidate(
            "qwen36_35b_a3b_vanch007",
            "vanch007/Huihui-Qwen3.6-35B-A3B-abliterated-mlx-4bit",
        ),
        Candidate(
            "qwen36_35b_a3b_nabichan",
            "nabi-chan/Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-MLX-4bit",
        ),
    ]


def cache_dir_for_model(model_ref: str) -> Path:
    safe = model_ref.replace("/", "--")
    return Path.home() / ".cache" / "huggingface" / "hub" / f"models--{safe}"


def is_model_cached(model_ref: str) -> bool:
    return cache_dir_for_model(model_ref).is_dir()


def _json_or_text(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def http_json(
    method: str,
    host: str,
    port: int,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _json_or_text(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json_or_text(exc.read())


def wait_process_http(
    proc: subprocess.Popen[Any],
    host: str,
    port: int,
    path: str,
    timeout_s: float,
    log: Any,
    label: str,
) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{label} exited before readiness: {proc.returncode}")
        try:
            status, body = http_json("GET", host, port, path, timeout=5)
            if 200 <= status < 300:
                log.write("http_ready", label=label, status=status, body=body)
                return
            last_error = {"status": status, "body": body}
        except Exception as exc:  # noqa: BLE001 - readiness diagnostics need exact error.
            last_error = repr(exc)
        time.sleep(2)
    raise TimeoutError(f"{label} did not become ready within {timeout_s}s: {last_error}")


def write_backend_env(candidate: Candidate) -> None:
    BACKEND_ENV.write_text(
        "\n".join(
            [
                f"export DFLASH_MODEL={candidate.target!r}",
                f"export DFLASH_DRAFT={candidate.draft!r}",
                "export DFLASH_PROFILE=${DFLASH_PROFILE:-balanced}",
                "export DFLASH_MAX_CTX=${DFLASH_MAX_CTX:-24000}",
                "export DFLASH_PREFILL_STEP_SIZE=${DFLASH_PREFILL_STEP_SIZE:-4096}",
                "export DFLASH_PREFIX_CACHE_MAX_ENTRIES=${DFLASH_PREFIX_CACHE_MAX_ENTRIES:-4}",
                "export DFLASH_PREFIX_CACHE_MAX_BYTES=${DFLASH_PREFIX_CACHE_MAX_BYTES:-8GB}",
                "export DFLASH_PREFIX_CACHE_L2=${DFLASH_PREFIX_CACHE_L2:-0}",
                "",
            ]
        ),
        encoding="utf-8",
    )


@contextmanager
def preserved_backend_env():
    old_text = None
    old_exists = BACKEND_ENV.exists()
    if old_exists:
        stat = BACKEND_ENV.stat()
        if stat.st_blocks > 0 or stat.st_size == 0:
            old_text = BACKEND_ENV.read_text(encoding="utf-8")
    try:
        yield
    finally:
        if not old_exists:
            with suppress(FileNotFoundError):
                BACKEND_ENV.unlink()
        elif old_text is not None:
            BACKEND_ENV.write_text(old_text, encoding="utf-8")


def _stop_process_group(proc: subprocess.Popen[Any], timeout_s: float = 20.0) -> None:
    if proc.poll() is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=timeout_s)


@contextmanager
def managed_gateway(args: Any, gateway_dir: Path, log: Any):
    gateway_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = gateway_dir / "gateway.stdout.log"
    stderr_path = gateway_dir / "gateway.stderr.log"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "DFLASH_GATEWAY_HOST": "127.0.0.1",
            "DFLASH_GATEWAY_PORT": str(args.gateway_port),
            "DFLASH_BACKEND_HOST": "127.0.0.1",
            "DFLASH_BACKEND_PORT": str(args.backend_port),
            "DFLASH_GATEWAY_IDLE_SECONDS": str(args.idle_seconds),
            "DFLASH_GATEWAY_STARTUP_TIMEOUT": str(args.start_timeout),
            "DFLASH_GATEWAY_PROXY_TIMEOUT": str(args.request_timeout),
            "DFLASH_GATEWAY_BACKEND_COMMAND": str(ROOT / "start-dflash-backend.command"),
            "DFLASH_GATEWAY_BACKEND_CWD": str(ROOT),
            "DFLASH_GATEWAY_ARTIFACT_DIR": str(gateway_dir / "events"),
        }
    )
    gateway_path = RELEASE_GATEWAY if RELEASE_GATEWAY.exists() else ROOT / "dflash_gateway.py"
    command = [str(ROOT / ".venv" / "bin" / "python"), str(gateway_path)]
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            preexec_fn=os.setsid,
        )
        log.write(
            "gateway_start",
            pid=proc.pid,
            port=args.gateway_port,
            backend_port=args.backend_port,
            gateway_path=str(gateway_path),
        )
        try:
            wait_process_http(
                proc,
                "127.0.0.1",
                args.gateway_port,
                "/health",
                args.start_timeout,
                log,
                "dflash-gateway",
            )
            yield proc
        finally:
            with suppress(Exception):
                http_json("POST", "127.0.0.1", args.gateway_port, "/gateway/stop?force=1", timeout=10)
            _stop_process_group(proc)
            log.write("gateway_stop", returncode=proc.returncode)
