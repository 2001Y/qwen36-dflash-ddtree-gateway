#!/usr/bin/env python3
"""Run ts-bench through OpenCode against local DFlash/DDTree endpoints."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parent
TS_BENCH_ROOT = Path("/private/tmp/ts-bench")
ENGINE_MATRIX_FILE = ROOT / "benchmark-engine-matrix.py"
ARTIFACT_ROOT = ROOT / ".artifacts" / "dflash" / "ts-bench-matrix"
TOP_25_EXERCISES = [
    "acronym",
    "anagram",
    "bank-account",
    "binary-search",
    "binary-search-tree",
    "bowling",
    "complex-numbers",
    "connect",
    "crypto-square",
    "diamond",
    "dnd-character",
    "flatten-array",
    "food-chain",
    "house",
    "pascals-triangle",
    "rational-numbers",
    "react",
    "rectangles",
    "relative-distance",
    "robot-name",
    "spiral-matrix",
    "transpose",
    "two-bucket",
    "variable-length-quantity",
    "wordy",
]


def load_engine_module():
    spec = importlib.util.spec_from_file_location("benchmark_engine_matrix", ENGINE_MATRIX_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {ENGINE_MATRIX_FILE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def is_top25_request(value: str) -> bool:
    return value.strip().lower() in {"", "default", "top25"}


def planned_exercises(args: argparse.Namespace) -> list[str | None]:
    if args.exercise_mode != "per-exercise":
        return [None]
    if is_top25_request(args.exercise):
        return TOP_25_EXERCISES
    exercises = parse_csv(args.exercise)
    if not exercises:
        raise SystemExit("--exercise-mode per-exercise requires at least one exercise")
    return exercises


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def run_text(command: list[str], timeout: float = 10.0) -> dict[str, Any]:
    started = now_ms()
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "returncode": proc.returncode,
            "duration_ms": now_ms() - started,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:  # noqa: BLE001 - benchmark gate must record exact failures
        return {
            "command": command,
            "returncode": None,
            "duration_ms": now_ms() - started,
            "error": repr(exc),
        }


def parse_system_free_percent(text: str) -> int | None:
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", text)
    if match is None:
        return None
    return int(match.group(1))


def sample_system_gate() -> dict[str, Any]:
    memory_pressure = run_text(["memory_pressure"], timeout=10)
    free_percent = None
    if memory_pressure.get("returncode") == 0:
        free_percent = parse_system_free_percent(str(memory_pressure.get("stdout", "")))
    return {
        "loadavg": os.getloadavg(),
        "memory_pressure": {
            "system_free_percent": free_percent,
            "raw_error": memory_pressure if memory_pressure.get("returncode") != 0 else None,
        },
    }


def check_system_gate(
    args: argparse.Namespace,
    log: Jsonl,
    engine: str,
    candidate: Any,
    stage: str,
) -> tuple[bool, dict[str, Any]]:
    sample = sample_system_gate()
    free_percent = sample["memory_pressure"]["system_free_percent"]
    min_free = args.min_system_free_percent
    ok = True
    reason = None
    if min_free > 0:
        if free_percent is None:
            ok = False
            reason = "memory_pressure_unavailable"
        elif free_percent < min_free:
            ok = False
            reason = "system_free_percent_below_threshold"
    log.write(
        "system_gate",
        engine=engine,
        candidate=candidate.name,
        stage=stage,
        ok=ok,
        reason=reason,
        min_system_free_percent=min_free,
        **sample,
    )
    return ok, {"reason": reason, **sample}


class Jsonl:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, event: str, **payload: Any) -> None:
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "ts_ms": now_ms(),
            "event": event,
            **payload,
        }
        self._fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def stop_process_group(proc: subprocess.Popen[Any], timeout_s: float = 20.0) -> None:
    if proc.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=timeout_s)


def write_opencode_config(config_home: Path, base_url: str, candidates: list[Any]) -> Path:
    config_dir = config_home / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    models = {
        candidate.target: {
            "name": candidate.name,
            "limit": {"context": 24000, "output": 8192},
        }
        for candidate in candidates
    }
    config = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "*": "allow",
            "bash": {"*": "allow"},
            "edit": "allow",
            "write": "allow",
            "patch": "allow",
        },
        "provider": {
            "local-llm": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local OpenAI-compatible LLM",
                "options": {
                    "baseURL": base_url,
                    "apiKey": "local",
                    "timeout": 900000,
                },
                "models": models,
            }
        },
    }
    path = config_dir / "opencode.jsonc"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_aider_shim(out_dir: Path) -> Path:
    bin_dir = out_dir / "tools" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "aider"
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "exec uvx --from aider-chat aider \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return bin_dir


def write_aider_model_files(out_dir: Path, candidates: list[Any]) -> tuple[Path, Path]:
    config_dir = out_dir / "aider-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, dict[str, Any]] = {}
    settings_lines: list[str] = []
    for candidate in candidates:
        model_id = model_id_for_agent("aider", candidate)
        metadata[model_id] = {
            "max_tokens": 32768,
            "max_input_tokens": 24576,
            "max_output_tokens": 8192,
            "input_cost_per_token": 0.0,
            "output_cost_per_token": 0.0,
            "litellm_provider": "openai",
            "mode": "chat",
        }
        settings_lines.extend(
            [
                f"- name: {model_id}",
                "  edit_format: whole",
                f"  weak_model_name: {model_id}",
                "  use_repo_map: false",
                "  send_undo_reply: false",
                "  streaming: false",
                "  use_temperature: false",
                "",
            ]
        )
    metadata_path = config_dir / "model-metadata.json"
    settings_path = config_dir / "model-settings.yml"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    settings_path.write_text("\n".join(settings_lines), encoding="utf-8")
    return settings_path, metadata_path


def load_ts_bench_output(output_dir: Path) -> dict[str, Any] | None:
    files = sorted(output_dir.glob("*.json"), key=lambda item: item.stat().st_mtime)
    if not files:
        return None
    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in data.get("results", []):
        rows.append(
            {
                "exercise": row.get("exercise"),
                "agentSuccess": row.get("agentSuccess"),
                "testSuccess": row.get("testSuccess"),
                "overallSuccess": row.get("overallSuccess"),
                "agentDuration": row.get("agentDuration"),
                "testDuration": row.get("testDuration"),
                "totalDuration": row.get("totalDuration"),
            }
        )
    return {
        "path": str(path),
        "summary": data.get("summary"),
        "results": rows,
    }


def model_id_for_agent(agent: str, candidate: Any) -> str:
    if agent == "opencode":
        return f"local-llm/{candidate.target}"
    if agent == "aider":
        return f"openai/{candidate.target}"
    raise ValueError(f"Unsupported ts-bench agent: {agent}")


def run_ts_bench(
    candidate: Any,
    engine: str,
    args: argparse.Namespace,
    out_dir: Path,
    config_home: Path,
    base_url: str,
    tools_bin: Path,
    aider_settings_path: Path,
    aider_metadata_path: Path,
    log: Jsonl,
    exercise: str | None = None,
    monitor_proc: subprocess.Popen[Any] | None = None,
) -> dict[str, Any]:
    run_dir = out_dir / f"{engine}-{candidate.name}"
    if exercise is not None:
        run_dir = run_dir / "exercises" / exercise
    run_dir.mkdir(parents=True, exist_ok=True)
    node_bin = Path(args.node_bin_dir).expanduser()
    env = os.environ.copy()
    env.update(
        {
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_DATA_HOME": str(run_dir / "xdg-data"),
            "XDG_CACHE_HOME": str(run_dir / "xdg-cache"),
            "HOME": str(run_dir / "home"),
            "COREPACK_HOME": str(run_dir / "corepack"),
            "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(out_dir / "uv-cache")),
            "UV_TOOL_DIR": os.environ.get("UV_TOOL_DIR", str(out_dir / "uv-tools")),
            "UV_TOOL_BIN_DIR": os.environ.get("UV_TOOL_BIN_DIR", str(out_dir / "uv-bin")),
            "OPENAI_API_KEY": "local",
            "OPENAI_API_BASE": base_url,
            "OPENAI_BASE_URL": base_url,
            "AIDER_ANALYTICS": "false",
            "AIDER_MODEL_SETTINGS_FILE": str(aider_settings_path),
            "AIDER_MODEL_METADATA_FILE": str(aider_metadata_path),
            "AIDER_SHOW_MODEL_WARNINGS": "false",
            "AIDER_CHECK_MODEL_ACCEPTS_SETTINGS": "false",
            "AIDER_MAP_TOKENS": "0",
            "AIDER_MAX_CHAT_HISTORY_TOKENS": "4096",
            "AIDER_TIMEOUT": str(args.request_timeout),
            "NO_COLOR": "1",
            "CI": "1",
            "PATH": f"{tools_bin}:{node_bin}:{ROOT / '.venv' / 'bin'}:{os.environ.get('PATH', '')}",
        }
    )
    model_id = model_id_for_agent(args.agent, candidate)
    command = [
        "bun",
        "src/index.ts",
        "--agent",
        args.agent,
        "--provider",
        "openai",
        "--model",
        model_id,
        "--timeout",
        str(args.ts_bench_timeout),
        "--version",
        args.agent_version,
        "--output-format",
        "json",
        "--output-dir",
        str((run_dir / "output").resolve()),
    ]
    if exercise is not None:
        command.extend(["--exercise", exercise])
    elif not is_top25_request(args.exercise):
        command.extend(["--exercise", args.exercise])
    if args.save_result:
        command.extend(
            [
                "--save-result",
                "--skip-leaderboard-refresh",
                "--result-dir",
                str(run_dir / "results"),
                "--result-name",
                f"{engine}-{candidate.name}",
            ]
        )
    started = now_ms()
    stdout_path = run_dir / "ts-bench.stdout.log"
    stderr_path = run_dir / "ts-bench.stderr.log"
    log.write(
        "ts_bench_start",
        engine=engine,
        candidate=candidate.name,
        agent=args.agent,
        base_url=base_url,
        model=model_id,
        command=command,
    )
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            command,
            cwd=TS_BENCH_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            preexec_fn=os.setsid,
        )
        monitor_failure: dict[str, Any] | None = None
        deadline = time.monotonic() + args.outer_timeout
        while True:
            returncode = proc.poll()
            if returncode is not None:
                break
            if monitor_proc is not None and monitor_proc.poll() is not None:
                monitor_failure = {
                    "pid": monitor_proc.pid,
                    "returncode": monitor_proc.returncode,
                }
                stop_process_group(proc)
                returncode = 125
                break
            if time.monotonic() >= deadline:
                stop_process_group(proc)
                returncode = 124
                break
            time.sleep(1)
    result = {
        "engine": engine,
        "candidate": candidate.name,
        "agent": args.agent,
        "model": model_id,
        "target": candidate.target,
        "draft": candidate.draft,
        "returncode": returncode,
        "elapsed_ms": now_ms() - started,
        "exercise": exercise,
        "exercise_mode": args.exercise_mode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    ts_bench_output = load_ts_bench_output(run_dir / "output")
    if ts_bench_output is not None:
        result["ts_bench_output"] = ts_bench_output
    if monitor_failure is not None:
        result.update(
            {
                "status": "infra_failed",
                "reason": "server_exited_during_ts_bench",
                "detail": monitor_failure,
            }
        )
    log.write("ts_bench_result", **result)
    return result


def dflash_gateway_metrics(
    candidate: Any,
    args: argparse.Namespace,
    engine_module: Any,
    log: Jsonl,
    stage: str,
) -> tuple[bool, dict[str, Any]]:
    status, body = engine_module.http_json(
        "GET",
        "127.0.0.1",
        args.gateway_port,
        "/gateway/metrics",
        timeout=20,
    )
    is_open = False
    if isinstance(body, dict):
        is_open = float(body.get("backend_crash_cooldown_remaining_seconds") or 0) > 0
    payload = {"http_status": status, "body": body}
    log.write(
        "dflash_gateway_metrics",
        candidate=candidate.name,
        stage=stage,
        circuit_open=is_open,
        **payload,
    )
    return is_open, payload


def infra_failed_result(
    candidate: Any,
    engine: str,
    reason: str,
    detail: dict[str, Any],
    exercise: str | None = None,
) -> dict[str, Any]:
    return {
        "engine": engine,
        "candidate": candidate.name,
        "model": candidate.target,
        "target": candidate.target,
        "draft": candidate.draft,
        "returncode": None,
        "elapsed_ms": 0,
        "status": "infra_failed",
        "reason": reason,
        "detail": detail,
        "exercise": exercise,
    }


def run_ts_bench_sequence(
    candidate: Any,
    engine: str,
    args: argparse.Namespace,
    out_dir: Path,
    config_home: Path,
    base_url: str,
    tools_bin: Path,
    aider_settings_path: Path,
    aider_metadata_path: Path,
    log: Jsonl,
    engine_module: Any,
    server_proc: subprocess.Popen[Any] | None = None,
) -> list[dict[str, Any]]:
    exercises = planned_exercises(args)
    results: list[dict[str, Any]] = []
    if exercises == [None]:
        return [
            run_ts_bench(
                candidate,
                engine,
                args,
                out_dir,
                config_home,
                base_url,
                tools_bin,
                aider_settings_path,
                aider_metadata_path,
                log,
            )
        ]

    for index, exercise in enumerate(exercises, start=1):
        assert exercise is not None
        ok, gate = check_system_gate(args, log, engine, candidate, f"before_exercise:{exercise}")
        if not ok:
            result = system_gate_failed_result(candidate, engine, gate)
            result.update(
                {
                    "exercise": exercise,
                    "exercise_index": index,
                    "exercise_count": len(exercises),
                }
            )
            results.append(result)
            log.write("ts_bench_result", **result)
            break

        result = run_ts_bench(
            candidate,
            engine,
            args,
            out_dir,
            config_home,
            base_url,
            tools_bin,
            aider_settings_path,
            aider_metadata_path,
            log,
            exercise=exercise,
            monitor_proc=server_proc,
        )
        result.update(
            {
                "exercise_index": index,
                "exercise_count": len(exercises),
            }
        )
        results.append(result)

        if engine == "dflash":
            circuit_open, detail = dflash_gateway_metrics(
                candidate,
                args,
                engine_module,
                log,
                f"after_exercise:{exercise}",
            )
            if circuit_open:
                stop_result = infra_failed_result(
                    candidate,
                    engine,
                    "dflash_gateway_crash_circuit_open",
                    detail,
                    exercise,
                )
                results.append(stop_result)
                log.write("ts_bench_result", **stop_result)
                break

        if server_proc is not None and server_proc.poll() is not None:
            if result.get("status") == "infra_failed" and result.get("reason") == "server_exited_during_ts_bench":
                break
            stop_result = infra_failed_result(
                candidate,
                engine,
                "server_exited_during_exercise_sequence",
                {"returncode": server_proc.returncode},
                exercise,
            )
            results.append(stop_result)
            log.write("ts_bench_result", **stop_result)
            break

    return results


def preflight_chat_payload(candidate: Any, max_tokens: int) -> dict[str, Any]:
    return {
        "model": candidate.target,
        "messages": [
            {
                "role": "user",
                "content": "Return exactly OK.",
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def preflight_dflash_candidate(
    candidate: Any,
    args: argparse.Namespace,
    engine_module: Any,
    log: Jsonl,
) -> bool:
    started = now_ms()
    log.write(
        "dflash_preflight_start",
        candidate=candidate.name,
        target=candidate.target,
        draft=candidate.draft,
        max_tokens=args.preflight_max_tokens,
        timeout=args.preflight_timeout,
    )
    try:
        status, body = engine_module.http_json(
            "POST",
            "127.0.0.1",
            args.gateway_port,
            "/v1/chat/completions",
            preflight_chat_payload(candidate, args.preflight_max_tokens),
            timeout=args.preflight_timeout,
        )
    except Exception as exc:  # noqa: BLE001 - benchmark harness must record startup failures
        elapsed_ms = now_ms() - started
        log.write(
            "dflash_preflight_failed",
            candidate=candidate.name,
            target=candidate.target,
            draft=candidate.draft,
            elapsed_ms=elapsed_ms,
            error=repr(exc),
        )
        return False

    elapsed_ms = now_ms() - started
    if status != 200:
        log.write(
            "dflash_preflight_failed",
            candidate=candidate.name,
            target=candidate.target,
            draft=candidate.draft,
            elapsed_ms=elapsed_ms,
            http_status=status,
            response=body,
        )
        return False

    log.write(
        "dflash_preflight_ok",
        candidate=candidate.name,
        target=candidate.target,
        draft=candidate.draft,
        elapsed_ms=elapsed_ms,
        http_status=status,
    )
    return True


def preflight_failed_result(candidate: Any, engine: str, reason: str) -> dict[str, Any]:
    return {
        "engine": engine,
        "candidate": candidate.name,
        "model": candidate.target,
        "target": candidate.target,
        "draft": candidate.draft,
        "returncode": None,
        "elapsed_ms": 0,
        "status": "preflight_failed",
        "reason": reason,
    }


def startup_failed_result(candidate: Any, engine: str, reason: str, error: str) -> dict[str, Any]:
    return {
        "engine": engine,
        "candidate": candidate.name,
        "model": candidate.target,
        "target": candidate.target,
        "draft": candidate.draft,
        "returncode": None,
        "elapsed_ms": 0,
        "status": "startup_failed",
        "reason": reason,
        "error": error,
    }


def system_gate_failed_result(candidate: Any, engine: str, gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "engine": engine,
        "candidate": candidate.name,
        "model": candidate.target,
        "target": candidate.target,
        "draft": candidate.draft,
        "returncode": None,
        "elapsed_ms": 0,
        "status": "system_gate_failed",
        "reason": gate.get("reason"),
        "system_gate": gate,
    }


@contextlib.contextmanager
def ddtree_server(candidate: Any, args: argparse.Namespace, out_dir: Path, engine_module: Any, log: Jsonl):
    stdout_path = out_dir / f"ddtree-{candidate.name}.stdout.log"
    stderr_path = out_dir / f"ddtree-{candidate.name}.stderr.log"
    command = " ".join(
        shlex.quote(part)
        for part in [
            f"PYTHONPATH={args.ddtree_root}",
            "DDTREE_EXACT_COMMIT=1",
            "PYTHONDONTWRITEBYTECODE=1",
            str(ROOT / ".venv" / "bin" / "python"),
            str(Path(args.ddtree_root) / "ddtree_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(args.ddtree_port),
            "--model",
            candidate.target,
            "--draft",
            candidate.draft,
            "--tree-budget",
            str(args.tree_budget),
        ]
    )
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        proc = subprocess.Popen(
            ["/bin/zsh", "-lic", command],
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            preexec_fn=os.setsid,
        )
        log.write("ddtree_start", candidate=candidate.name, pid=proc.pid, port=args.ddtree_port)
        try:
            engine_module.wait_process_http(
                proc,
                "127.0.0.1",
                args.ddtree_port,
                "/health",
                args.start_timeout,
                log,
                f"ddtree:{candidate.name}",
            )
            yield proc
        finally:
            stop_process_group(proc)
            log.write("ddtree_stop", candidate=candidate.name, returncode=proc.returncode)


def select_candidates(engine_module: Any, args: argparse.Namespace) -> list[Any]:
    candidates = engine_module.load_candidates()
    if args.candidates != "all":
        selected_names = parse_csv(args.candidates)
        by_name = {candidate.name: candidate for candidate in candidates}
        missing = [name for name in selected_names if name not in by_name]
        if missing:
            raise SystemExit(f"Unknown candidates: {', '.join(missing)}")
        candidates = [by_name[name] for name in selected_names]
    if args.cached_only:
        candidates = [
            candidate
            for candidate in candidates
            if engine_module.is_model_cached(candidate.target)
            and engine_module.is_model_cached(candidate.draft)
        ]
    return candidates


def supports_ddtree(candidate: Any) -> bool:
    """Current local DDTree patch supports Qwen-family targets, not Gemma4."""
    marker = f"{candidate.target} {candidate.draft}".lower()
    return "qwen" in marker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", default="dflash,ddtree")
    parser.add_argument("--candidates", default="all")
    parser.add_argument("--cached-only", action="store_true")
    parser.add_argument(
        "--exercise",
        default="acronym",
        help="ts-bench exercise slug, comma list, numeric count, or top25/default to use ts-bench's built-in TOP_25 selection",
    )
    parser.add_argument(
        "--exercise-mode",
        default="monolithic",
        choices=["monolithic", "per-exercise"],
        help="run selected exercises in one ts-bench process or one process per exercise with a system gate before each one",
    )
    parser.add_argument("--agent", default="aider", choices=["aider", "opencode"])
    parser.add_argument("--ts-bench-timeout", type=int, default=900)
    parser.add_argument("--agent-version", default="0.0.0")
    parser.add_argument("--outer-timeout", type=int, default=1200)
    parser.add_argument("--save-result", action="store_true")
    parser.add_argument("--gateway-port", type=int, default=8200)
    parser.add_argument("--backend-port", type=int, default=8201)
    parser.add_argument("--ddtree-port", type=int, default=8216)
    parser.add_argument("--ddtree-root", default="/private/tmp/ddtree-mlx")
    parser.add_argument("--tree-budget", type=int, default=2)
    parser.add_argument("--start-timeout", type=int, default=900)
    parser.add_argument("--request-timeout", type=int, default=3600)
    parser.add_argument("--preflight-timeout", type=int, default=1200)
    parser.add_argument("--preflight-max-tokens", type=int, default=1)
    parser.add_argument(
        "--min-system-free-percent",
        type=int,
        default=0,
        help="fail candidate before heavy work when memory_pressure reports a lower system free percentage; 0 disables the gate",
    )
    parser.add_argument("--node-bin-dir", default="/tmp/codex-mise-data/installs/node/22.22.2/bin")
    parser.add_argument("--out-dir")
    args = parser.parse_args()

    engine_module = load_engine_module()
    engines = set(parse_csv(args.engines))
    candidates = select_candidates(engine_module, args)
    if not candidates:
        raise SystemExit("No candidates selected")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = (Path(args.out_dir) if args.out_dir else ARTIFACT_ROOT / stamp).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    log = Jsonl(out_dir / "results.jsonl")
    results: list[dict[str, Any]] = []
    config_home = out_dir / "opencode-config"
    tools_bin = write_aider_shim(out_dir)
    aider_settings_path, aider_metadata_path = write_aider_model_files(out_dir, candidates)
    try:
        log.write(
            "run_start",
            engines=sorted(engines),
            candidates=[candidate.name for candidate in candidates],
            args=vars(args),
        )
        if "dflash" in engines:
            dflash_base_url = f"http://127.0.0.1:{args.gateway_port}/v1"
            if args.agent == "opencode":
                write_opencode_config(config_home, dflash_base_url, candidates)
            gateway_dir = out_dir / "dflash-gateway"
            gateway_dir.mkdir(parents=True, exist_ok=True)
            gateway_args = argparse.Namespace(
                gateway_port=args.gateway_port,
                backend_port=args.backend_port,
                idle_seconds=300,
                start_timeout=args.start_timeout,
                request_timeout=args.request_timeout,
            )
            with engine_module.preserved_backend_env(), engine_module.managed_gateway(
                gateway_args,
                gateway_dir,
                log,
            ):
                for candidate in candidates:
                    if not engine_module.is_model_cached(candidate.target):
                        log.write("skip_missing_target", engine="dflash", candidate=candidate.name)
                        continue
                    ok, gate = check_system_gate(args, log, "dflash", candidate, "before_preflight")
                    if not ok:
                        result = system_gate_failed_result(candidate, "dflash", gate)
                        results.append(result)
                        log.write("ts_bench_result", **result)
                        continue
                    engine_module.write_backend_env(candidate)
                    engine_module.http_json(
                        "POST",
                        "127.0.0.1",
                        args.gateway_port,
                        "/gateway/stop?force=1",
                        timeout=20,
                    )
                    if not preflight_dflash_candidate(candidate, args, engine_module, log):
                        engine_module.http_json(
                            "POST",
                            "127.0.0.1",
                            args.gateway_port,
                            "/gateway/stop?force=1",
                            timeout=20,
                        )
                        result = preflight_failed_result(
                            candidate,
                            "dflash",
                            "backend did not pass minimal chat preflight",
                        )
                        results.append(result)
                        log.write("ts_bench_result", **result)
                        continue
                    ok, gate = check_system_gate(args, log, "dflash", candidate, "before_ts_bench")
                    if not ok:
                        result = system_gate_failed_result(candidate, "dflash", gate)
                        results.append(result)
                        log.write("ts_bench_result", **result)
                        continue
                    sequence_results = run_ts_bench_sequence(
                        candidate,
                        "dflash",
                        args,
                        out_dir,
                        config_home,
                        dflash_base_url,
                        tools_bin,
                        aider_settings_path,
                        aider_metadata_path,
                        log,
                        engine_module,
                    )
                    results.extend(sequence_results)
                    if any(
                        result.get("status") == "infra_failed"
                        and result.get("reason") == "dflash_gateway_crash_circuit_open"
                        for result in sequence_results
                    ):
                        log.write(
                            "engine_abort",
                            engine="dflash",
                            candidate=candidate.name,
                            reason="dflash_gateway_crash_circuit_open",
                        )
                        break
        if "ddtree" in engines:
            ddtree_base_url = f"http://127.0.0.1:{args.ddtree_port}/v1"
            if args.agent == "opencode":
                write_opencode_config(config_home, ddtree_base_url, candidates)
            for candidate in candidates:
                if not engine_module.is_model_cached(candidate.target):
                    log.write("skip_missing_target", engine="ddtree", candidate=candidate.name)
                    continue
                if not supports_ddtree(candidate):
                    log.write(
                        "skip_incompatible",
                        engine="ddtree",
                        candidate=candidate.name,
                        reason="current local DDTree verification path supports Qwen-family targets only",
                    )
                    continue
                ok, gate = check_system_gate(args, log, "ddtree", candidate, "before_start")
                if not ok:
                    result = system_gate_failed_result(candidate, "ddtree", gate)
                    results.append(result)
                    log.write("ts_bench_result", **result)
                    continue
                try:
                    with ddtree_server(candidate, args, out_dir, engine_module, log) as proc:
                        results.extend(
                            run_ts_bench_sequence(
                                candidate,
                                "ddtree",
                                args,
                                out_dir,
                                config_home,
                                ddtree_base_url,
                                tools_bin,
                                aider_settings_path,
                                aider_metadata_path,
                                log,
                                engine_module,
                                server_proc=proc,
                            )
                        )
                except Exception as exc:  # noqa: BLE001 - candidate-level benchmark failure must be logged and continued
                    result = startup_failed_result(
                        candidate,
                        "ddtree",
                        "server did not pass startup health check",
                        repr(exc),
                    )
                    results.append(result)
                    log.write("ts_bench_result", **result)
                    continue
        (out_dir / "summary.json").write_text(
            json.dumps({"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.write("run_end", out_dir=str(out_dir), result_count=len(results))
        print(str(out_dir))
        return 0
    finally:
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
