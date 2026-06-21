from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AcceptanceCheck:
    name: str
    cwd: Path
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    kind: str = "command"

    def as_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "cwd": self.cwd.relative_to(REPO_ROOT).as_posix(),
            "command": self.command,
            "env": self.env,
            "kind": self.kind,
        }


def _backend_python() -> str:
    return os.getenv(
        "SHOPGUIDE_BACKEND_PYTHON",
        str(REPO_ROOT / "env" / "venv_shopguide_backend" / "bin" / "python"),
    )


def build_checks(health_port: str = "18083") -> list[AcceptanceCheck]:
    backend_python = _backend_python()
    java_home = os.getenv("JAVA_HOME", "/home/huadabioa/houlong/android-studio/jbr")
    android_home = os.getenv("ANDROID_HOME", "/home/huadabioa/houlong/android-sdk")
    android_env = {
        "JAVA_HOME": java_home,
        "ANDROID_HOME": android_home,
        "ANDROID_SDK_ROOT": os.getenv("ANDROID_SDK_ROOT", android_home),
        "PATH": f"{java_home}/bin:{android_home}/platform-tools:{os.environ.get('PATH', '')}",
    }

    health_env = {
        "HOST": "127.0.0.1",
        "PORT": health_port,
        "USE_EMBEDDING": "0",
        "TTS_ENABLED": "false",
        "STT_ENABLED": "false",
        "ARK_API_KEY": "",
        "LLM_API_KEY": "",
    }

    return [
        AcceptanceCheck(
            name="backend-tests",
            cwd=REPO_ROOT / "server",
            command=[backend_python, "-m", "pytest", "-q"],
        ),
        AcceptanceCheck(
            name="eval-runner",
            cwd=REPO_ROOT / "server",
            command=[
                backend_python,
                "scripts/run_eval.py",
                "--scenarios",
                "../data/eval/shopguide_core_scenarios.json",
            ],
        ),
        AcceptanceCheck(
            name="android-build",
            cwd=REPO_ROOT / "client",
            command=["./gradlew", ":app:testDebugUnitTest", ":app:assembleDebug", "--no-daemon"],
            env=android_env,
        ),
        AcceptanceCheck(
            name="script-syntax",
            cwd=REPO_ROOT,
            command=[
                "bash",
                "-c",
                (
                    "for script in "
                    "start_backend.sh "
                    "server/scripts/setup_backend_env.sh "
                    "server/scripts/start_backend.sh "
                    "server/scripts/start_stt.sh "
                    "client/gradlew; "
                    'do bash -n "$script"; done'
                ),
            ],
        ),
        AcceptanceCheck(
            name="host-health-smoke",
            cwd=REPO_ROOT,
            command=["bash", "server/scripts/start_backend.sh"],
            env=health_env,
            kind="health-smoke",
        ),
    ]


def _select_checks(all_checks: list[AcceptanceCheck], names: list[str] | None) -> tuple[list[AcceptanceCheck], int]:
    if not names:
        return all_checks, 0

    checks_by_name = {check.name: check for check in all_checks}
    unknown = [name for name in names if name not in checks_by_name]
    if unknown:
        valid = ", ".join(check.name for check in all_checks)
        print(f"Unknown check: {unknown[0]}. Valid checks: {valid}", file=sys.stderr)
        return [], 2

    return [checks_by_name[name] for name in names], 0


def _merged_env(extra: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(extra)
    return env


def _run_command(check: AcceptanceCheck, timeout_seconds: int) -> int:
    print(f"== {check.name} ==", flush=True)
    print("cwd:", check.cwd.relative_to(REPO_ROOT).as_posix(), flush=True)
    print("command:", " ".join(check.command), flush=True)
    result = subprocess.run(
        check.command,
        cwd=check.cwd,
        env=_merged_env(check.env),
        timeout=timeout_seconds,
        check=False,
    )
    return result.returncode


def _run_health_smoke(check: AcceptanceCheck, health_timeout_seconds: int) -> int:
    env = _merged_env(check.env)
    port = env["PORT"]
    url = f"http://127.0.0.1:{port}/health"
    print(f"== {check.name} ==", flush=True)
    print("cwd:", check.cwd.relative_to(REPO_ROOT).as_posix(), flush=True)
    print("command:", " ".join(check.command), flush=True)
    print("health:", url, flush=True)

    process = subprocess.Popen(check.command, cwd=check.cwd, env=env)
    try:
        deadline = time.monotonic() + health_timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                print(f"Backend smoke process exited early with code {process.returncode}", file=sys.stderr)
                return process.returncode or 1
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    body = response.read().decode("utf-8", errors="replace")
                if response.status == 200 and '"status"' in body:
                    print(body, flush=True)
                    return 0
            except (urllib.error.URLError, TimeoutError):
                time.sleep(1)
        print(f"Timed out waiting for {url}", file=sys.stderr)
        return 1
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def run_checks(checks: list[AcceptanceCheck], timeout_seconds: int, health_timeout_seconds: int) -> int:
    for check in checks:
        if check.kind == "health-smoke":
            code = _run_health_smoke(check, health_timeout_seconds)
        else:
            code = _run_command(check, timeout_seconds)
        if code != 0:
            print(f"Check failed: {check.name} exited with {code}", file=sys.stderr)
            return code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SoulDance release acceptance matrix.")
    parser.add_argument("--list-checks", action="store_true", help="Print the full acceptance matrix as JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected checks without running them.")
    parser.add_argument("--check", action="append", help="Run only this check name. May be repeated.")
    parser.add_argument("--timeout-seconds", type=int, default=1200, help="Per-command timeout for normal checks.")
    parser.add_argument("--health-timeout-seconds", type=int, default=45, help="Timeout for host health smoke.")
    parser.add_argument("--health-port", default=os.getenv("SHOPGUIDE_HEALTH_PORT", "18083"))
    args = parser.parse_args(argv)

    all_checks = build_checks(health_port=args.health_port)
    if args.list_checks:
        print(json.dumps([check.as_json() for check in all_checks], ensure_ascii=False, indent=2))
        return 0

    selected_checks, status = _select_checks(all_checks, args.check)
    if status != 0:
        return status

    if args.dry_run:
        print(json.dumps([check.as_json() for check in selected_checks], ensure_ascii=False, indent=2))
        return 0

    return run_checks(selected_checks, args.timeout_seconds, args.health_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
