#!/usr/bin/env python3
"""On-demand OpenAI-compatible gateway for dflash-mlx.

The gateway keeps the public endpoint stable on port 8000 while spawning the
heavy DFlash backend only when a generation request arrives. It then stops the
backend after an idle timeout.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

GATEWAY_HOST = os.environ.get("DFLASH_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("DFLASH_GATEWAY_PORT", "8000"))
BACKEND_HOST = os.environ.get("DFLASH_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("DFLASH_BACKEND_PORT", "8001"))
BACKEND_BASE = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
MODEL_ID = os.environ.get(
    "DFLASH_MODEL",
    "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
)
IDLE_SECONDS = int(os.environ.get("DFLASH_GATEWAY_IDLE_SECONDS", "300"))
STARTUP_TIMEOUT = int(os.environ.get("DFLASH_GATEWAY_STARTUP_TIMEOUT", "1800"))
PROXY_TIMEOUT = int(os.environ.get("DFLASH_GATEWAY_PROXY_TIMEOUT", "3600"))
STOP_GRACE_SECONDS = float(os.environ.get("DFLASH_GATEWAY_STOP_GRACE_SECONDS", "15"))
CRASH_WINDOW_SECONDS = int(os.environ.get("DFLASH_GATEWAY_CRASH_WINDOW_SECONDS", "900"))
CRASH_LIMIT = int(os.environ.get("DFLASH_GATEWAY_CRASH_LIMIT", "3"))
CRASH_COOLDOWN_SECONDS = int(os.environ.get("DFLASH_GATEWAY_CRASH_COOLDOWN_SECONDS", "300"))
MODELS_START_BACKEND = os.environ.get("DFLASH_GATEWAY_MODELS_START_BACKEND", "0") in {
    "1",
    "true",
    "yes",
}
BACKEND_COMMAND = os.environ.get(
    "DFLASH_GATEWAY_BACKEND_COMMAND",
    str(ROOT / "scripts" / "start-dflash-backend.command"),
)
BACKEND_CWD = Path(os.environ.get("DFLASH_GATEWAY_BACKEND_CWD", str(ROOT))).resolve()
ARTIFACT_DIR = Path(
    os.environ.get("DFLASH_GATEWAY_ARTIFACT_DIR", str(ROOT / ".artifacts" / "dflash" / "gateway"))
)
EVENT_LOG = ARTIFACT_DIR / "events.jsonl"

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class GatewayState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.proc: subprocess.Popen[bytes] | None = None
        self.backend_log_path: Path | None = None
        self.last_activity = time.time()
        self.started_at: float | None = None
        self.crashes: list[float] = []
        self.cooldown_until = 0.0
        self.request_count = 0


STATE = GatewayState()


def now_ms() -> int:
    return int(time.time() * 1000)


def write_event(level: str, event: str, **fields: Any) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ts_ms": now_ms(),
        "level": level,
        "event": event,
        **fields,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def backend_url(path: str) -> str:
    return f"{BACKEND_BASE}{path}"


def backend_is_alive() -> bool:
    proc = STATE.proc
    return proc is not None and proc.poll() is None


def note_backend_exit_if_needed() -> None:
    proc = STATE.proc
    if proc is None:
        return
    code = proc.poll()
    if code is None:
        return
    crashed_at = time.time()
    STATE.crashes.append(crashed_at)
    cutoff = crashed_at - CRASH_WINDOW_SECONDS
    STATE.crashes = [ts for ts in STATE.crashes if ts >= cutoff]
    write_event(
        "ERROR",
        "backend_exited",
        returncode=code,
        crash_count=len(STATE.crashes),
        backend_log=str(STATE.backend_log_path) if STATE.backend_log_path else None,
    )
    STATE.proc = None
    STATE.started_at = None
    if len(STATE.crashes) >= CRASH_LIMIT:
        STATE.cooldown_until = crashed_at + CRASH_COOLDOWN_SECONDS
        write_event(
            "ERROR",
            "crash_circuit_open",
            cooldown_seconds=CRASH_COOLDOWN_SECONDS,
            crash_limit=CRASH_LIMIT,
        )


def wait_for_backend_ready(deadline: float) -> None:
    last_error = ""
    while time.time() < deadline:
        with STATE.lock:
            note_backend_exit_if_needed()
            if STATE.proc is None:
                raise RuntimeError(f"backend exited before ready: {last_error}")
        try:
            request = urllib.request.Request(backend_url("/v1/models"), method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                if 200 <= response.status < 300:
                    write_event("SUCCESS", "backend_ready", status=response.status)
                    return
        except Exception as exc:  # noqa: BLE001 - log the exact readiness failure.
            last_error = repr(exc)
        time.sleep(2)
    raise TimeoutError(f"backend did not become ready within {STARTUP_TIMEOUT}s: {last_error}")


def ensure_backend() -> None:
    with STATE.lock:
        STATE.last_activity = time.time()
        note_backend_exit_if_needed()
        if backend_is_alive():
            return
        now = time.time()
        if now < STATE.cooldown_until:
            remaining = int(STATE.cooldown_until - now)
            raise RuntimeError(f"dflash gateway crash circuit is open for {remaining}s")
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        STATE.backend_log_path = ARTIFACT_DIR / f"backend-{time.strftime('%Y%m%d-%H%M%S')}.log"
        backend_log = STATE.backend_log_path.open("ab", buffering=0)
        command = shlex.split(BACKEND_COMMAND)
        env = os.environ.copy()
        env.setdefault("DFLASH_HOST", BACKEND_HOST)
        env.setdefault("DFLASH_PORT", str(BACKEND_PORT))
        write_event(
            "INFO",
            "backend_start",
            command=command,
            cwd=str(BACKEND_CWD),
            backend_log=str(STATE.backend_log_path),
        )
        STATE.proc = subprocess.Popen(
            command,
            cwd=str(BACKEND_CWD),
            env=env,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        STATE.started_at = now
    wait_for_backend_ready(time.time() + STARTUP_TIMEOUT)


def stop_backend(force: bool = False, reason: str = "manual") -> dict[str, Any]:
    with STATE.lock:
        proc = STATE.proc
        if proc is None:
            return {"stopped": False, "reason": reason, "message": "backend_not_running"}
        pid = proc.pid
        write_event("INFO", "backend_stop_begin", pid=pid, force=force, reason=reason)
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            STATE.proc = None
            return {"stopped": False, "reason": reason, "message": "process_not_found"}

    deadline = time.time() + STOP_GRACE_SECONDS
    while time.time() < deadline:
        if proc.poll() is not None:
            with STATE.lock:
                STATE.proc = None
                STATE.started_at = None
            write_event("SUCCESS", "backend_stop_done", pid=pid, returncode=proc.returncode)
            return {"stopped": True, "pid": pid, "returncode": proc.returncode, "reason": reason}
        time.sleep(0.2)

    if force:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
        with STATE.lock:
            STATE.proc = None
            STATE.started_at = None
        write_event("WARNING", "backend_stop_killed", pid=pid, returncode=proc.returncode)
        return {"stopped": True, "pid": pid, "returncode": proc.returncode, "reason": reason}

    write_event("WARNING", "backend_stop_timeout", pid=pid, reason=reason)
    return {"stopped": False, "pid": pid, "reason": reason, "message": "stop_timeout"}


def idle_reaper() -> None:
    while True:
        time.sleep(5)
        with STATE.lock:
            note_backend_exit_if_needed()
            idle_for = time.time() - STATE.last_activity
            should_stop = STATE.proc is not None and STATE.proc.poll() is None and idle_for >= IDLE_SECONDS
        if should_stop:
            stop_backend(force=True, reason="idle_timeout")


def response_model_list() -> dict[str, Any]:
    with STATE.lock:
        running = backend_is_alive()
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "owned_by": "dflash-gateway",
            }
        ],
        "gateway": {
            "backend_running": running,
            "backend_base_url": BACKEND_BASE,
            "idle_seconds": IDLE_SECONDS,
        },
    }


def gateway_metrics() -> dict[str, Any]:
    with STATE.lock:
        proc = STATE.proc
        running = proc is not None and proc.poll() is None
        return {
            "gateway": {
                "host": GATEWAY_HOST,
                "port": GATEWAY_PORT,
                "model": MODEL_ID,
                "request_count": STATE.request_count,
            },
            "backend": {
                "base_url": BACKEND_BASE,
                "running": running,
                "pid": proc.pid if running and proc else None,
                "started_at": STATE.started_at,
                "last_activity": STATE.last_activity,
                "idle_seconds": IDLE_SECONDS,
                "backend_log": str(STATE.backend_log_path) if STATE.backend_log_path else None,
            },
            "crash_circuit": {
                "crash_count": len(STATE.crashes),
                "cooldown_until": STATE.cooldown_until,
            },
        }


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "DFlashOnDemandGateway/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        write_event("INFO", "http_access", client=self.client_address[0], message=format % args)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_error_json(self, status: int, message: str, **fields: Any) -> None:
        self.send_json(status, {"error": {"message": message, "type": "gateway_error"}, **fields})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/gateway/metrics":
            self.send_json(200, gateway_metrics())
            return
        if parsed.path == "/health":
            self.send_json(200, {"status": "ok", "backend_running": backend_is_alive()})
            return
        if parsed.path == "/v1/models" and not MODELS_START_BACKEND:
            self.send_json(200, response_model_list())
            return
        if parsed.path.startswith("/v1/"):
            self.proxy()
            return
        self.send_error_json(404, "not found")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/gateway/stop":
            params = urllib.parse.parse_qs(parsed.query)
            force = params.get("force", ["0"])[0] in {"1", "true", "yes"}
            self.send_json(200, stop_backend(force=force, reason="manual"))
            return
        if parsed.path.startswith("/v1/"):
            self.proxy()
            return
        self.send_error_json(404, "not found")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization,content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def proxy(self) -> None:
        body = self.read_body()
        request_started = time.time()
        with STATE.lock:
            STATE.request_count += 1
            STATE.last_activity = request_started
        try:
            ensure_backend()
        except Exception as exc:  # noqa: BLE001
            write_event("ERROR", "backend_ensure_failed", error=repr(exc), path=self.path)
            self.send_error_json(503, str(exc))
            return

        upstream_url = backend_url(self.path)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        request = urllib.request.Request(
            upstream_url,
            data=body if self.command in {"POST", "PUT", "PATCH"} else None,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(request, timeout=PROXY_TIMEOUT) as response:
                data = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in HOP_BY_HOP_HEADERS:
                        self.send_header(key, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
                elapsed_ms = int((time.time() - request_started) * 1000)
                with STATE.lock:
                    STATE.last_activity = time.time()
                write_event(
                    "SUCCESS",
                    "proxy_done",
                    method=self.command,
                    path=self.path,
                    status=response.status,
                    elapsed_ms=elapsed_ms,
                    bytes=len(data),
                )
        except urllib.error.HTTPError as exc:
            data = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            write_event("WARNING", "proxy_http_error", path=self.path, status=exc.code, bytes=len(data))
        except Exception as exc:  # noqa: BLE001
            write_event("ERROR", "proxy_failed", path=self.path, error=repr(exc))
            self.send_error_json(502, f"backend request failed: {exc!r}")


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=idle_reaper, name="idle-reaper", daemon=True).start()
    server = ThreadingHTTPServer((GATEWAY_HOST, GATEWAY_PORT), GatewayHandler)
    write_event(
        "SUCCESS",
        "gateway_listening",
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        backend_base=BACKEND_BASE,
        idle_seconds=IDLE_SECONDS,
        model=MODEL_ID,
    )
    print(f"DFlash on-demand gateway listening on http://{GATEWAY_HOST}:{GATEWAY_PORT}", flush=True)
    print(f"Backend target: {BACKEND_BASE}", flush=True)
    print(f"Logs: {EVENT_LOG}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_backend(force=True, reason="gateway_shutdown")
        server.server_close()
        write_event("INFO", "gateway_shutdown")


if __name__ == "__main__":
    main()

