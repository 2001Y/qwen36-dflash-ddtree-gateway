#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import http.client
import http.server
import json
import os
import shlex
import signal
import socket
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value)


def read_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return float(value)


def read_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.lower() not in {"0", "false", "no", "off"}


@dataclasses.dataclass(frozen=True)
class ModelSpec:
    id: str
    draft: str
    owned_by: str = "dflash"


def model_cache_dir(cache_root: Path, model_id: str) -> Path:
    return cache_root / f"models--{model_id.replace('/', '--')}"


def model_id_from_cache_dir(path: Path) -> str | None:
    name = path.name
    if not name.startswith("models--"):
        return None
    parts = name.removeprefix("models--").split("--", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


def has_hf_snapshot(path: Path) -> bool:
    snapshots = path / "snapshots"
    if not snapshots.is_dir():
        return False
    return any(child.is_dir() for child in snapshots.iterdir())


def hf_hub_cache_root() -> Path:
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser() / "hub"
    return Path(os.environ.get("HF_HUB_CACHE", "~/.cache/huggingface/hub")).expanduser()


def infer_draft_model(model_id: str) -> str | None:
    lowered = model_id.lower()
    if "dflash" in lowered:
        return None
    if "qwen3.6-35b-a3b" in lowered:
        return "z-lab/Qwen3.6-35B-A3B-DFlash"
    if "qwen3.6-27b" in lowered:
        return "z-lab/Qwen3.6-27B-DFlash"
    if "gemma-4-26" in lowered or "gemma4-26" in lowered:
        return "z-lab/gemma-4-26B-A4B-it-DFlash"
    return None


def parse_model_specs_json(raw: str) -> tuple[ModelSpec, ...]:
    data = json.loads(raw)
    if isinstance(data, dict):
        iterable = [
            {"id": key, **value} if isinstance(value, dict) else {"id": key, "draft": value}
            for key, value in data.items()
        ]
    elif isinstance(data, list):
        iterable = data
    else:
        raise ValueError("DFLASH_GATEWAY_MODELS_JSON must be a list or object")

    specs: list[ModelSpec] = []
    for item in iterable:
        if isinstance(item, str):
            draft = infer_draft_model(item)
            if draft is None:
                raise ValueError(f"Cannot infer DFlash draft for model: {item}")
            specs.append(ModelSpec(id=item, draft=draft))
            continue
        if not isinstance(item, dict):
            raise ValueError("Each model spec must be a string or object")
        model_id = item.get("id") or item.get("model")
        draft = item.get("draft")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("Model spec requires id")
        if not isinstance(draft, str) or not draft:
            inferred = infer_draft_model(model_id)
            if inferred is None:
                raise ValueError(f"Model spec requires draft: {model_id}")
            draft = inferred
        owned_by = item.get("owned_by", "dflash")
        specs.append(ModelSpec(id=model_id, draft=draft, owned_by=str(owned_by)))
    return dedupe_model_specs(specs)


def parse_model_specs_pairs(raw: str) -> tuple[ModelSpec, ...]:
    specs: list[ModelSpec] = []
    for chunk in raw.replace("\n", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        if "=" in item:
            model_id, draft = item.split("=", 1)
            specs.append(ModelSpec(id=model_id.strip(), draft=draft.strip()))
            continue
        draft = infer_draft_model(item)
        if draft is None:
            raise ValueError(f"Cannot infer DFlash draft for model: {item}")
        specs.append(ModelSpec(id=item, draft=draft))
    return dedupe_model_specs(specs)


def read_env_file_value(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    prefix = f"export {name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix):].strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            return value[1:-1]
        return value
    return None


def dedupe_model_specs(specs: list[ModelSpec]) -> tuple[ModelSpec, ...]:
    seen: set[str] = set()
    deduped: list[ModelSpec] = []
    for spec in specs:
        if spec.id in seen:
            continue
        seen.add(spec.id)
        deduped.append(spec)
    return tuple(deduped)


def discover_local_model_specs(workspace: Path) -> tuple[ModelSpec, ...]:
    raw_json = os.environ.get("DFLASH_GATEWAY_MODELS_JSON")
    if raw_json:
        return parse_model_specs_json(raw_json)

    raw_pairs = os.environ.get("DFLASH_GATEWAY_MODEL_SPECS")
    if raw_pairs:
        return parse_model_specs_pairs(raw_pairs)

    cache_root = hf_hub_cache_root()
    specs: list[ModelSpec] = []
    if cache_root.is_dir():
        for path in sorted(cache_root.glob("models--*")):
            if not path.is_dir() or not has_hf_snapshot(path):
                continue
            model_id = model_id_from_cache_dir(path)
            if model_id is None:
                continue
            draft = infer_draft_model(model_id)
            if draft is None:
                continue
            if not has_hf_snapshot(model_cache_dir(cache_root, draft)):
                continue
            specs.append(ModelSpec(id=model_id, draft=draft))

    if specs:
        return dedupe_model_specs(specs)

    model_id = os.environ.get("DFLASH_MODEL") or read_env_file_value(workspace / ".dflash-backend.env", "DFLASH_MODEL")
    draft = os.environ.get("DFLASH_DRAFT") or read_env_file_value(workspace / ".dflash-backend.env", "DFLASH_DRAFT")
    if model_id and draft:
        return (ModelSpec(id=model_id, draft=draft),)
    return ()


def models_payload(specs: tuple[ModelSpec, ...]) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": spec.id,
                "object": "model",
                "created": 0,
                "owned_by": spec.owned_by,
            }
            for spec in specs
        ],
    }


@dataclasses.dataclass(frozen=True)
class GatewayConfig:
    workspace: Path
    models: tuple[ModelSpec, ...]
    host: str
    port: int
    backend_host: str
    backend_port: int
    backend_command: str
    start_backend: bool
    start_timeout_s: float
    idle_timeout_s: float
    shutdown_grace_s: float
    request_timeout_s: float
    ready_timeout_s: float
    poll_interval_s: float
    max_backend_crashes: int
    crash_window_s: float
    crash_cooldown_s: float
    default_chat_max_tokens: int
    force_disable_thinking: bool
    log_path: Path
    backend_log_path: Path

    @property
    def backend_base_url(self) -> str:
        return f"http://{self.backend_host}:{self.backend_port}"

    @property
    def default_model(self) -> ModelSpec | None:
        return self.models[0] if self.models else None

    def model_spec(self, model_id: str | None) -> ModelSpec | None:
        if model_id is None or model_id == "":
            return self.default_model
        for spec in self.models:
            if spec.id == model_id:
                return spec
        return None

    @classmethod
    def from_env(cls, script_dir: Path) -> "GatewayConfig":
        workspace = Path(os.environ.get("DFLASH_GATEWAY_WORKSPACE", str(script_dir))).expanduser().resolve()
        log_path = Path(
            os.environ.get("DFLASH_GATEWAY_LOG", str(workspace / ".artifacts/dflash/gateway/events.jsonl"))
        ).expanduser()
        backend_log_path = Path(
            os.environ.get("DFLASH_GATEWAY_BACKEND_LOG", str(workspace / ".artifacts/dflash/gateway/backend.log"))
        ).expanduser()
        backend_command = os.environ.get(
            "DFLASH_GATEWAY_BACKEND_COMMAND",
            str(workspace / "start-dflash-backend.command"),
        )
        return cls(
            workspace=workspace,
            models=discover_local_model_specs(workspace),
            host=os.environ.get("DFLASH_GATEWAY_HOST", "127.0.0.1"),
            port=read_int("DFLASH_GATEWAY_PORT", 8000),
            backend_host=os.environ.get("DFLASH_BACKEND_HOST", "127.0.0.1"),
            backend_port=read_int("DFLASH_BACKEND_PORT", 8001),
            backend_command=backend_command,
            start_backend=read_bool("DFLASH_GATEWAY_START_BACKEND", True),
            start_timeout_s=read_float("DFLASH_GATEWAY_START_TIMEOUT", 900.0),
            idle_timeout_s=read_float("DFLASH_GATEWAY_IDLE_SECONDS", 300.0),
            shutdown_grace_s=read_float("DFLASH_GATEWAY_SHUTDOWN_GRACE", 30.0),
            request_timeout_s=read_float("DFLASH_GATEWAY_REQUEST_TIMEOUT", 3600.0),
            ready_timeout_s=read_float("DFLASH_GATEWAY_READY_TIMEOUT", 3.0),
            poll_interval_s=read_float("DFLASH_GATEWAY_POLL_INTERVAL", 1.0),
            max_backend_crashes=read_int("DFLASH_GATEWAY_MAX_BACKEND_CRASHES", 3),
            crash_window_s=read_float("DFLASH_GATEWAY_CRASH_WINDOW_SECONDS", 300.0),
            crash_cooldown_s=read_float("DFLASH_GATEWAY_CRASH_COOLDOWN_SECONDS", 1800.0),
            default_chat_max_tokens=read_int("DFLASH_GATEWAY_DEFAULT_CHAT_MAX_TOKENS", 4096),
            force_disable_thinking=read_bool("DFLASH_GATEWAY_FORCE_DISABLE_THINKING", True),
            log_path=log_path,
            backend_log_path=backend_log_path,
        )


class JsonLogger:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, level: str, event: str, **fields: object) -> None:
        record = {"ts": utc_now(), "level": level, "event": event, **fields}
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        with self.lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


class GatewayError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class BackendManager:
    def __init__(self, config: GatewayConfig, logger: JsonLogger):
        self.config = config
        self.logger = logger
        self.process: subprocess.Popen[bytes] | None = None
        self.active_model: ModelSpec | None = None
        self.state = "stopped"
        self.last_activity = time.monotonic()
        self.in_flight = 0
        self.crash_times: list[float] = []
        self.crash_block_until: float | None = None
        self.lock = threading.RLock()
        self.start_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.idle_thread = threading.Thread(target=self._idle_loop, name="dflash-gateway-idle", daemon=True)
        self.idle_thread.start()

    def shutdown(self) -> None:
        self.stop_event.set()
        self.stop_backend(reason="gateway_shutdown")

    def mark_request_start(self) -> None:
        with self.lock:
            self.in_flight += 1

    def mark_request_end(self) -> None:
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.last_activity = time.monotonic()

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            process = self.process
            pid = process.pid if process and process.poll() is None else None
            last_idle_s = round(time.monotonic() - self.last_activity, 3)
            cooldown_remaining_s = self._crash_cooldown_remaining_locked(time.monotonic())
            return {
                "state": self.state,
                "gateway": f"http://{self.config.host}:{self.config.port}",
                "backend": self.config.backend_base_url,
                "backend_pid": pid,
                "backend_owned": process is not None,
                "active_model": self.active_model.id if self.active_model else None,
                "active_draft": self.active_model.draft if self.active_model else None,
                "available_models": [spec.id for spec in self.config.models],
                "in_flight": self.in_flight,
                "idle_seconds": last_idle_s,
                "idle_timeout_seconds": self.config.idle_timeout_s,
                "start_backend": self.config.start_backend,
                "backend_crash_count": len(self.crash_times),
                "backend_crash_window_seconds": self.config.crash_window_s,
                "backend_crash_cooldown_remaining_seconds": cooldown_remaining_s,
            }

    def ensure_ready(self, request_id: str, model: ModelSpec) -> None:
        with self.lock:
            running_different_model = (
                self.process is not None
                and self.process.poll() is None
                and self.active_model is not None
                and self.active_model != model
            )
            active_model = self.active_model.id if self.active_model else None
            in_flight = self.in_flight
        if running_different_model:
            if in_flight > 1:
                raise GatewayError(409, "Cannot switch models while another request is in flight")
            self.logger.write(
                "INFO",
                "backend_model_switch",
                request_id=request_id,
                from_model=active_model,
                to_model=model.id,
                to_draft=model.draft,
            )
            self.stop_backend(reason="model_switch", force=True)

        if self._probe_backend() and self._backend_matches(model):
            self._set_ready_from_probe()
            return

        with self.start_lock:
            if self._probe_backend() and self._backend_matches(model):
                self._set_ready_from_probe()
                return

            if self._probe_backend() and not self._backend_matches(model):
                with self.lock:
                    active_model = self.active_model.id if self.active_model else None
                    in_flight = self.in_flight
                if active_model is None:
                    raise GatewayError(
                        409,
                        "A backend is already running but the gateway does not own its model state; stop it before switching models",
                    )
                if in_flight > 1:
                    raise GatewayError(409, "Cannot switch models while another request is in flight")
                self.logger.write(
                    "INFO",
                    "backend_model_switch",
                    request_id=request_id,
                    from_model=active_model,
                    to_model=model.id,
                    to_draft=model.draft,
                )
                self.stop_backend(reason="model_switch", force=True)

            with self.lock:
                process = self.process
                if process is not None and process.poll() is not None:
                    self._record_backend_exit_locked(
                        request_id=request_id,
                        event="backend_exited_before_ready",
                        process=process,
                    )
                    self.process = None
                    self.active_model = None
                    self.state = "failed"

            self._raise_if_crash_circuit_open(request_id)

            if not self.config.start_backend:
                raise GatewayError(503, "Backend is not running and gateway auto-start is disabled")

            with self.lock:
                should_spawn = self.process is None or self.process.poll() is not None
            if should_spawn:
                self._spawn_backend(request_id, model)

            deadline = time.monotonic() + self.config.start_timeout_s
            last_log = 0.0
            while time.monotonic() < deadline:
                if self._probe_backend():
                    with self.lock:
                        self.state = "ready"
                        self.active_model = model
                        pid = self.process.pid if self.process else None
                    self.logger.write(
                        "SUCCESS",
                        "backend_ready",
                        request_id=request_id,
                        pid=pid,
                        model=model.id,
                        draft=model.draft,
                    )
                    return

                with self.lock:
                    process = self.process
                    if process is None:
                        self.state = "failed"
                        self.logger.write(
                            "ERROR",
                            "backend_missing_during_start",
                            request_id=request_id,
                        )
                        raise GatewayError(503, "Backend exited during startup")
                    if process.poll() is not None:
                        self.state = "failed"
                        self._record_backend_exit_locked(
                            request_id=request_id,
                            event="backend_exited_during_start",
                            process=process,
                        )
                        self.process = None
                        self.active_model = None
                        raise GatewayError(503, "Backend exited during startup")

                now = time.monotonic()
                if now - last_log >= 15:
                    self.logger.write("INFO", "backend_start_wait", request_id=request_id)
                    last_log = now
                time.sleep(self.config.poll_interval_s)

            with self.lock:
                self.state = "failed"
            raise GatewayError(503, "Backend did not become ready before startup timeout")

    def backend_is_ready(self) -> bool:
        if not self._probe_backend():
            return False
        self._set_ready_from_probe()
        return True

    def stop_backend(self, reason: str, force: bool = False) -> dict[str, object]:
        with self.lock:
            process = self.process
            if process is None:
                self.state = "stopped" if self.state != "external_ready" else "external_ready"
                return {"stopped": False, "reason": "no_owned_backend"}
            if self.in_flight > 0 and reason != "gateway_shutdown" and not force:
                return {"stopped": False, "reason": "requests_in_flight", "in_flight": self.in_flight}
            self.state = "stopping"
            pid = process.pid

        self.logger.write("INFO", "backend_stop_start", reason=reason, pid=pid, force=force)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=self.config.shutdown_grace_s)
            except subprocess.TimeoutExpired:
                self.logger.write("WARNING", "backend_stop_kill", reason=reason, pid=pid, force=force)
                process.kill()
                process.wait(timeout=10)

        exit_code = process.returncode
        with self.lock:
            if self.process is process:
                self.process = None
                self.active_model = None
                self.state = "stopped"
                self.last_activity = time.monotonic()
        self.logger.write("SUCCESS", "backend_stop_end", reason=reason, pid=pid, exit_code=exit_code, force=force)
        return {"stopped": True, "pid": pid, "exit_code": exit_code}

    def _spawn_backend(self, request_id: str, model: ModelSpec) -> None:
        command = shlex.split(self.config.backend_command)
        if not command:
            raise GatewayError(500, "DFLASH_GATEWAY_BACKEND_COMMAND is empty")

        env = os.environ.copy()
        env["DFLASH_HOST"] = self.config.backend_host
        env["DFLASH_PORT"] = str(self.config.backend_port)
        env["DFLASH_MODEL"] = model.id
        env["DFLASH_DRAFT"] = model.draft
        self.config.backend_log_path.parent.mkdir(parents=True, exist_ok=True)
        backend_log = self.config.backend_log_path.open("ab")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.config.workspace),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=backend_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            backend_log.close()
            self.logger.write(
                "ERROR",
                "backend_spawn_failed",
                request_id=request_id,
                command=command,
                error=repr(exc),
            )
            raise GatewayError(500, f"Failed to spawn backend: {exc}") from exc

        backend_log.close()
        with self.lock:
            self.process = process
            self.active_model = model
            self.state = "starting"
            self.last_activity = time.monotonic()
        self.logger.write(
            "INFO",
            "backend_spawned",
            request_id=request_id,
            pid=process.pid,
            command=command,
            model=model.id,
            draft=model.draft,
        )

    def _set_ready_from_probe(self) -> None:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.state = "ready"
            else:
                self.state = "external_ready"
            self.last_activity = time.monotonic()

    def _probe_backend(self) -> bool:
        try:
            conn = http.client.HTTPConnection(
                self.config.backend_host,
                self.config.backend_port,
                timeout=self.config.ready_timeout_s,
            )
            conn.request("GET", "/v1/models", headers={"Connection": "close"})
            response = conn.getresponse()
            response.read()
            return 200 <= response.status < 300
        except OSError:
            return False
        finally:
            with contextlib.suppress(Exception):
                conn.close()  # type: ignore[name-defined]

    def _backend_matches(self, model: ModelSpec) -> bool:
        with self.lock:
            return self.active_model == model

    def _idle_loop(self) -> None:
        while not self.stop_event.wait(5):
            with self.lock:
                process = self.process
                if process is None or process.poll() is not None:
                    if process is not None:
                        self._record_backend_exit_locked(
                            request_id=None,
                            event="backend_process_exited",
                            process=process,
                        )
                        self.process = None
                        self.active_model = None
                        self.state = "failed" if self.state == "starting" else "stopped"
                    continue
                if self.state not in {"ready", "failed"}:
                    continue
                idle_s = time.monotonic() - self.last_activity
                if self.in_flight > 0 or idle_s < self.config.idle_timeout_s:
                    continue
            self.stop_backend(reason="idle_timeout")

    def _crash_cooldown_remaining_locked(self, now: float) -> float:
        if self.crash_block_until is None:
            return 0.0
        remaining = self.crash_block_until - now
        if remaining <= 0:
            self.crash_block_until = None
            self._prune_crashes_locked(now)
            return 0.0
        return round(remaining, 3)

    def _raise_if_crash_circuit_open(self, request_id: str) -> None:
        with self.lock:
            remaining = self._crash_cooldown_remaining_locked(time.monotonic())
            crash_count = len(self.crash_times)
        if remaining <= 0:
            return
        self.logger.write(
            "ERROR",
            "backend_crash_circuit_reject",
            request_id=request_id,
            crash_count=crash_count,
            crash_window_s=self.config.crash_window_s,
            cooldown_remaining_s=remaining,
        )
        raise GatewayError(
            503,
            f"Backend auto-start paused after repeated crashes; retry after {remaining:.1f}s",
        )

    def _record_backend_exit_locked(
        self,
        request_id: str | None,
        event: str,
        process: subprocess.Popen[bytes],
    ) -> None:
        exit_code = process.returncode
        level = "ERROR" if exit_code not in {0, None} else "INFO"
        self.logger.write(
            level,
            event,
            request_id=request_id,
            pid=process.pid,
            exit_code=exit_code,
            state=self.state,
        )
        if exit_code in {0, None} or self.config.max_backend_crashes <= 0:
            return

        now = time.monotonic()
        self.crash_times.append(now)
        self._prune_crashes_locked(now)
        crash_count = len(self.crash_times)
        self.logger.write(
            "ERROR",
            "backend_crash_recorded",
            request_id=request_id,
            pid=process.pid,
            exit_code=exit_code,
            crash_count=crash_count,
            max_backend_crashes=self.config.max_backend_crashes,
            crash_window_s=self.config.crash_window_s,
        )
        if crash_count >= self.config.max_backend_crashes:
            self.crash_block_until = now + self.config.crash_cooldown_s
            self.logger.write(
                "ERROR",
                "backend_crash_circuit_open",
                request_id=request_id,
                crash_count=crash_count,
                crash_window_s=self.config.crash_window_s,
                cooldown_s=self.config.crash_cooldown_s,
            )

    def _prune_crashes_locked(self, now: float) -> None:
        cutoff = now - self.config.crash_window_s
        self.crash_times = [ts for ts in self.crash_times if ts >= cutoff]


class GatewayServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[http.server.BaseHTTPRequestHandler], manager: BackendManager, logger: JsonLogger):
        super().__init__(address, handler)
        self.manager = manager
        self.logger = logger
        self.config = manager.config


class GatewayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DFlashOnDemandGateway/1.0"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/gateway/"):
            self._send_json(200, {})
            return
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    @property
    def manager(self) -> BackendManager:
        return self.server.manager  # type: ignore[attr-defined]

    @property
    def logger(self) -> JsonLogger:
        return self.server.logger  # type: ignore[attr-defined]

    @property
    def config(self) -> GatewayConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        self.logger.write("DEBUG", "http_access", client=self.client_address[0], message=fmt % args)

    def _select_model_for_request(
        self,
        request_id: str,
        route: str,
        content_type: str,
        body: bytes | None,
    ) -> ModelSpec:
        requested_model: str | None = None
        if route == "/v1/chat/completions" and body and "application/json" in content_type.lower():
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise GatewayError(400, f"Invalid JSON request body: {exc}") from exc
            if isinstance(payload, dict):
                value = payload.get("model")
                if isinstance(value, str):
                    requested_model = value

        model = self.config.model_spec(requested_model)
        if model is None:
            self.logger.write(
                "ERROR",
                "unsupported_model",
                request_id=request_id,
                requested_model=requested_model,
                available_models=[spec.id for spec in self.config.models],
            )
            raise GatewayError(404, f"Unsupported DFlash model: {requested_model}")

        self.logger.write(
            "INFO",
            "request_model_selected",
            request_id=request_id,
            requested_model=requested_model,
            model=model.id,
            draft=model.draft,
        )
        return model

    def _handle(self) -> None:
        request_id = self.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.monotonic()
        route = urlsplit(self.path).path
        if route == "/" or route == "/gateway/health":
            self._send_json(200, {"ok": True, **self.manager.snapshot()}, request_id=request_id)
            return
        if route == "/gateway/metrics":
            self._send_json(200, self.manager.snapshot(), request_id=request_id)
            return
        if route == "/v1/models" and self.command in {"GET", "HEAD"}:
            self._send_json(200, models_payload(self.config.models), request_id=request_id)
            return
        if route == "/gateway/stop" and self.command == "POST":
            params = parse_qs(urlsplit(self.path).query)
            force = (params.get("force") or ["0"])[0].lower() in {"1", "true", "yes", "on"}
            result = self.manager.stop_backend(reason="manual", force=force)
            self._send_json(200, {"ok": True, **result, **self.manager.snapshot()}, request_id=request_id)
            return

        self.manager.mark_request_start()
        request_bytes = 0
        response_status = 0
        try:
            self.logger.write(
                "INFO",
                "request_start",
                request_id=request_id,
                method=self.command,
                path=self.path,
                client=self.client_address[0],
            )
            request_bytes = self._content_length()
            body = self.rfile.read(request_bytes) if request_bytes > 0 else None
            if route == "/metrics":
                if not self.manager.backend_is_ready():
                    raise GatewayError(503, "Backend metrics unavailable because backend is not ready")
            else:
                model = self._select_model_for_request(
                    request_id=request_id,
                    route=route,
                    content_type=self.headers.get("Content-Type", ""),
                    body=body,
                )
                self.manager.ensure_ready(request_id, model)
            response_status = self._proxy(request_id, body)
        except GatewayError as exc:
            response_status = exc.status
            self.logger.write("ERROR", "request_gateway_error", request_id=request_id, status=exc.status, error=exc.message)
            self._send_json(exc.status, {"error": exc.message, "request_id": request_id}, request_id=request_id)
        except Exception as exc:
            response_status = 502
            self.logger.write("ERROR", "request_unhandled_error", request_id=request_id, error=repr(exc))
            self._send_json(502, {"error": "Gateway proxy failed", "request_id": request_id}, request_id=request_id)
        finally:
            self.manager.mark_request_end()
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            self.logger.write(
                "SUCCESS" if 200 <= response_status < 500 else "ERROR",
                "request_end",
                request_id=request_id,
                method=self.command,
                path=self.path,
                request_bytes=request_bytes,
                status=response_status,
                duration_ms=duration_ms,
            )

    def _content_length(self) -> int:
        transfer_encoding = self.headers.get("Transfer-Encoding", "")
        if transfer_encoding and transfer_encoding.lower() != "identity":
            raise GatewayError(501, "Chunked request bodies are not supported by this gateway")
        value = self.headers.get("Content-Length")
        if value is None or value == "":
            return 0
        try:
            return int(value)
        except ValueError as exc:
            raise GatewayError(400, "Invalid Content-Length") from exc

    def _proxy(self, request_id: str, body: bytes | None) -> int:
        route = urlsplit(self.path).path
        request_content_type = self.headers.get("Content-Type", "")
        body = self._normalize_chat_request(
            request_id=request_id,
            route=route,
            content_type=request_content_type,
            body=body,
        )
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() not in {"host", "content-length"}
        }
        headers["Host"] = f"{self.config.backend_host}:{self.config.backend_port}"
        headers["Connection"] = "close"
        headers["X-Request-ID"] = request_id
        if body is not None:
            headers["Content-Length"] = str(len(body))

        conn = http.client.HTTPConnection(
            self.config.backend_host,
            self.config.backend_port,
            timeout=self.config.request_timeout_s,
        )
        headers_sent = False
        backend_status = 0
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
            backend_status = response.status
            content_type = response.getheader("Content-Type", "")
            if self.command == "HEAD" or "text/event-stream" in content_type.lower():
                self._send_proxy_headers(response)
                headers_sent = True
                total = self._copy_response_body(response)
                normalized_choices = 0
            else:
                raw_body = response.read()
                body, normalized_choices = self._normalize_chat_response(
                    request_id=request_id,
                    route=route,
                    content_type=content_type,
                    body=raw_body,
                )
                self._send_proxy_headers(response, content_length=len(body))
                headers_sent = True
                total = len(body)
                if body:
                    self.wfile.write(body)
                    self.wfile.flush()
            self.close_connection = True
            self.logger.write(
                "SUCCESS",
                "proxy_response",
                request_id=request_id,
                status=response.status,
                response_bytes=total,
                normalized_choices=normalized_choices,
            )
            return response.status
        except (OSError, http.client.HTTPException, socket.timeout) as exc:
            self.logger.write("ERROR", "proxy_failed", request_id=request_id, error=repr(exc))
            if headers_sent:
                self.close_connection = True
                return backend_status or 502
            raise GatewayError(502, "Backend proxy request failed") from exc
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    def _normalize_chat_request(
        self,
        request_id: str,
        route: str,
        content_type: str,
        body: bytes | None,
    ) -> bytes | None:
        if route != "/v1/chat/completions" or body is None or "application/json" not in content_type.lower():
            return body

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self.logger.write(
                "WARNING",
                "request_normalize_skipped",
                request_id=request_id,
                route=route,
                reason="json_decode_error",
                error=str(exc),
            )
            return body

        if not isinstance(payload, dict):
            return body

        added_max_tokens = False
        if "max_tokens" not in payload and "max_completion_tokens" not in payload:
            payload["max_tokens"] = self.config.default_chat_max_tokens
            added_max_tokens = True

        added_disable_thinking = False
        if self.config.force_disable_thinking:
            chat_template_kwargs = payload.get("chat_template_kwargs")
            if chat_template_kwargs is None:
                payload["chat_template_kwargs"] = {"enable_thinking": False}
                added_disable_thinking = True
            elif isinstance(chat_template_kwargs, dict) and "enable_thinking" not in chat_template_kwargs:
                chat_template_kwargs["enable_thinking"] = False
                added_disable_thinking = True

        if not added_max_tokens and not added_disable_thinking:
            return body

        rewritten = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.logger.write(
            "SUCCESS",
            "request_normalized",
            request_id=request_id,
            route=route,
            model=payload.get("model"),
            stream=payload.get("stream"),
            added_max_tokens=added_max_tokens,
            default_chat_max_tokens=self.config.default_chat_max_tokens if added_max_tokens else None,
            added_disable_thinking=added_disable_thinking,
            original_bytes=len(body),
            rewritten_bytes=len(rewritten),
        )
        return rewritten

    def _send_proxy_headers(self, response: http.client.HTTPResponse, content_length: int | None = None) -> None:
        self.send_response(response.status, response.reason)
        self.send_header("Connection", "close")
        for key, value in response.getheaders():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered in {"server", "date", "content-length"}:
                continue
            self.send_header(key, value)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.end_headers()

    def _normalize_chat_response(
        self,
        request_id: str,
        route: str,
        content_type: str,
        body: bytes,
    ) -> tuple[bytes, int]:
        if route != "/v1/chat/completions" or "application/json" not in content_type.lower() or not body:
            return body, 0

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self.logger.write(
                "WARNING",
                "response_normalize_skipped",
                request_id=request_id,
                route=route,
                reason="json_decode_error",
                error=str(exc),
            )
            return body, 0

        if not isinstance(payload, dict):
            return body, 0
        choices = payload.get("choices")
        if not isinstance(choices, list):
            return body, 0

        normalized = 0
        reasoning_chars = 0
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            reasoning = message.get("reasoning")
            empty_content = content is None or content == "" or content == []
            if not empty_content or not isinstance(reasoning, str) or reasoning == "":
                continue
            message["content"] = reasoning
            normalized += 1
            reasoning_chars += len(reasoning)

        if normalized == 0:
            return body, 0

        rewritten = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.logger.write(
            "SUCCESS",
            "response_normalized",
            request_id=request_id,
            route=route,
            source_field="message.reasoning",
            target_field="message.content",
            normalized_choices=normalized,
            source_chars=reasoning_chars,
            original_bytes=len(body),
            rewritten_bytes=len(rewritten),
        )
        return rewritten, normalized

    def _copy_response_body(self, response: http.client.HTTPResponse) -> int:
        if self.command == "HEAD":
            response.read()
            return 0

        total = 0
        content_type = response.getheader("Content-Type", "").lower()
        if "text/event-stream" in content_type:
            while True:
                line = response.readline(64 * 1024)
                if not line:
                    break
                total += len(line)
                self.wfile.write(line)
                self.wfile.flush()
            return total

        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            self.wfile.write(chunk)
            self.wfile.flush()
        return total

    def _send_json(self, status: int, payload: dict[str, object], request_id: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type,X-Request-ID")
        if request_id:
            self.send_header("X-Request-ID", request_id)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="On-demand gateway for dflash-mlx OpenAI-compatible server")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    config = GatewayConfig.from_env(script_dir)
    logger = JsonLogger(config.log_path)
    if args.check:
        print(json.dumps(dataclasses.asdict(config), default=str, ensure_ascii=False, indent=2))
        return 0

    manager = BackendManager(config, logger)
    server = GatewayServer((config.host, config.port), GatewayHandler, manager, logger)
    logger.write(
        "INFO",
        "gateway_start",
        gateway=f"http://{config.host}:{config.port}",
        backend=config.backend_base_url,
        backend_command=shlex.split(config.backend_command),
        models=[dataclasses.asdict(spec) for spec in config.models],
        idle_timeout_s=config.idle_timeout_s,
        max_backend_crashes=config.max_backend_crashes,
        crash_window_s=config.crash_window_s,
        crash_cooldown_s=config.crash_cooldown_s,
    )
    print(f"DFlash on-demand gateway listening on http://{config.host}:{config.port}")
    print(f"Backend target: {config.backend_base_url}")
    print(f"Logs: {config.log_path}")

    def handle_signal(signum: int, _frame: object) -> None:
        logger.write("INFO", "gateway_signal", signal=signum)
        threading.Thread(target=server.shutdown, name="dflash-gateway-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        manager.shutdown()
        server.server_close()
        logger.write("SUCCESS", "gateway_stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
