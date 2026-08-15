#!/usr/bin/env python3
"""Full startup for the jarvis-dev environment.

Brings up the whole docker-compose stack (jarvis-dev, postgres-age, authsome,
authsome-postgres, authsome-redis), waits for health checks, makes sure the
FastAPI app is actually serving inside jarvis-dev, and prints a summary of
where everything is reachable (including the Tailscale IP, if configured).

Usage:
    python development/scripts/startup.py [--build] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
ENV_TEMPLATE = REPO_ROOT / ".env.template"

HEALTHY_SERVICES = ["postgres-age", "authsome", "authsome-postgres", "authsome-redis"]
APP_CONTAINER = "jarvis-dev"


def run(*args: str, check: bool = True, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=check)


def ensure_env_file() -> bool:
    if ENV_FILE.exists():
        return True
    if ENV_TEMPLATE.exists():
        print(f"[!] {ENV_FILE} not found — copying from {ENV_TEMPLATE.name}. Fill in real secrets before continuing.")
        shutil.copy(ENV_TEMPLATE, ENV_FILE)
        return False
    print(f"[!] Neither {ENV_FILE} nor {ENV_TEMPLATE} exist — cannot start without configuration.", file=sys.stderr)
    return False


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run("docker", "compose", *args, check=check)


def container_health(name: str) -> str:
    result = run(
        "docker", "inspect", "--format", "{{.State.Health.Status}}", name, check=False
    )
    if result.returncode != 0:
        return "missing"
    return result.stdout.strip() or "none"


def container_running(name: str) -> bool:
    result = run("docker", "inspect", "--format", "{{.State.Running}}", name, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def wait_for_health(services: list[str], timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    pending = set(services)
    while pending and time.monotonic() < deadline:
        for name in list(pending):
            status = container_health(name)
            if status == "healthy":
                print(f"[✓] {name} is healthy")
                pending.discard(name)
            elif status == "missing":
                print(f"[!] {name} container not found", file=sys.stderr)
                pending.discard(name)
        if pending:
            time.sleep(3)
    if pending:
        print(f"[!] Timed out waiting for: {', '.join(sorted(pending))}", file=sys.stderr)
        return False
    return True


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def ensure_fastapi_running(timeout: int) -> bool:
    """The entrypoint starts uvicorn on container start; restart it if it died."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if http_ok("http://localhost:8000"):
            return True
        time.sleep(2)

    print("[!] FastAPI not responding on :8000 — attempting to (re)start it inside the container...")
    run(
        "docker", "exec", APP_CONTAINER, "bash", "-c",
        "pkill -f uvicorn; cd /workspace/jarvis && "
        "nohup uvicorn app:app --host 0.0.0.0 --port 8000 --log-level info "
        "> /tmp/fastapi.log 2>&1 &",
        check=False,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if http_ok("http://localhost:8000"):
            return True
        time.sleep(2)
    return False


def tailscale_ip() -> str | None:
    result = run("docker", "exec", APP_CONTAINER, "tailscale", "ip", "-4", check=False)
    ip = result.stdout.strip()
    return ip if result.returncode == 0 and ip else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Rebuild images before starting")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for health checks")
    args = parser.parse_args()

    if shutil.which("docker") is None:
        print("[!] docker CLI not found on PATH", file=sys.stderr)
        return 1

    if not ensure_env_file():
        print("[!] Fill in .env with real secrets, then re-run this script.", file=sys.stderr)
        return 1

    print("[*] Validating docker-compose.yml...")
    validate = compose("config", "--quiet", check=False)
    if validate.returncode != 0:
        print(validate.stderr, file=sys.stderr)
        return 1

    up_args = ["up", "-d"]
    if args.build:
        up_args.append("--build")
    print(f"[*] Starting stack: docker compose {' '.join(up_args)}")
    up = compose(*up_args, check=False)
    print(up.stdout)
    if up.returncode != 0:
        print(up.stderr, file=sys.stderr)
        return 1

    print("[*] Waiting for dependent services to become healthy...")
    if not wait_for_health(HEALTHY_SERVICES, args.timeout):
        print("[!] Continuing anyway — check `docker compose logs` for details.", file=sys.stderr)

    if not container_running(APP_CONTAINER):
        print(f"[!] {APP_CONTAINER} is not running", file=sys.stderr)
        return 1

    print("[*] Checking FastAPI app...")
    if not ensure_fastapi_running(args.timeout):
        print("[!] FastAPI never came up — check `docker exec jarvis-dev tail -f /tmp/fastapi.log`", file=sys.stderr)
        return 1
    print("[✓] FastAPI is responding on :8000")

    ts_ip = tailscale_ip()

    print()
    print("=" * 50)
    print("  JARVIS READY")
    print("=" * 50)
    print("  code-server  : http://localhost:8443")
    print("  FastAPI GUI  : http://localhost:8000")
    print("  Authsome UI  : http://localhost:7998")
    print("  PostgreSQL   : localhost:5432 (db: jarvis)")
    if ts_ip:
        print(f"  Tailscale    : http://{ts_ip}:8000  /  http://{ts_ip}:8443  (reachable from your phone)")
    else:
        print("  Tailscale    : not connected (set TAILSCALE_AUTHKEY in .env)")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
