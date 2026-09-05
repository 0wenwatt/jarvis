#!/usr/bin/env python3
"""Simplified startup for the jarvis-dev environment.

Brings up the whole docker-compose stack, waits for health checks, makes sure 
the FastAPI app is serving, and prints a summary.

Usage:
    python development/scripts/startup.py [--build] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
ENV_TEMPLATE = REPO_ROOT / ".env.template"
WORKSPACE_DIR = REPO_ROOT / "workspace" / "jarvis"

HEALTHY_SERVICES = ["postgres-age", "authsome", "authsome-postgres", "authsome-redis"]
APP_CONTAINER = "jarvis-dev"
CONTAINER_WORKSPACE = "/workspace/jarvis"


def run(*args: str, check: bool = True, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="ignore", check=check)


def ensure_docker_running() -> bool:
    print("[*] Checking if Docker daemon is running...")
    
    # Quick check if docker CLI exists
    if shutil.which("docker") is None:
        print("[!] Error: 'docker' CLI not found on PATH.", file=sys.stderr)
        return False

    # Test if Docker daemon is responsive
    res = run("docker", "info", check=False)
    if res.returncode == 0:
        print("[✓] Docker daemon is running.")
        return True

    print("[!] Docker daemon is not responding. Attempting to start Docker automatically...")
    
    system = platform.system()
    try:
        if system == "Windows":
            # Common paths for Docker Desktop on Windows
            docker_desktop_paths = [
                Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe",
                Path(os.environ.get("LocalAppData", "C:\\Users")) / "AppData" / "Local" / "Docker" / "Docker Desktop.exe"
            ]
            launched = False
            for path in docker_desktop_paths:
                if path.exists():
                    print(f"[*] Launching Docker Desktop from: {path}")
                    subprocess.Popen([str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    launched = True
                    break
            
            if not launched:
                # Fallback to standard command or service start
                subprocess.run(["net", "start", "com.docker.service"], capture_output=True)
                
        elif system == "Darwin": # macOS
            subprocess.run(["open", "-a", "Docker"], capture_output=True)
        elif system == "Linux":
            subprocess.run(["sudo", "systemctl", "start", "docker"], capture_output=True)

        print("[*] Waiting for Docker daemon to become responsive (up to 60s)...")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            time.sleep(5)
            if run("docker", "info", check=False).returncode == 0:
                print("[✓] Docker daemon successfully started and connected.")
                return True
                
    except Exception as e:
        print(f"[!] Failed to automatically start Docker: {e}", file=sys.stderr)

    print("[!] Error: Could not connect to Docker. Please start Docker Desktop/Daemon manually and re-run.", file=sys.stderr)
    return False


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


def check_and_cleanup_conflicts() -> bool:
    print("[*] Checking for port conflicts and existing containers...")
    required_ports = [5432, 8000, 8443, 7998]
    conflicting_containers = []

    try:
        inspect_res = run("docker", "ps", "-a", "--format", "{{.ID}}|{{.Names}}|{{.Ports}}", check=False)
        if inspect_res.returncode == 0 and inspect_res.stdout.strip():
            for line in inspect_res.stdout.strip().splitlines():
                parts = line.split("|")
                if len(parts) == 3:
                    c_id, c_name, c_ports = parts
                    for port in required_ports:
                        if f":{port}->" in c_ports or f":{port} " in c_ports:
                            conflicting_containers.append((c_name, port, c_id))

        if conflicting_containers:
            print(f"\n[!] Port Conflict Detected! Active/stopped containers are binding required ports:")
            for c_name, port, c_id in conflicting_containers:
                print(f"    - Container '{c_name}' ({c_id[:12]}) is using port {port}")
            
            print("\n[*] Automatically cleaning up conflicting containers...")
            for c_name, _, c_id in conflicting_containers:
                stop_res = run("docker", "rm", "-f", c_id, check=False)
                if stop_res.returncode == 0:
                    print(f"[✓] Removed conflicting container: {c_name} ({c_id[:12]})")
                else:
                    print(f"[!] Warning: Failed to remove container {c_name}: {stop_res.stderr.strip()}", file=sys.stderr)

        result = run("docker", "compose", "ps", "-a", "-q", check=False)
        if result.returncode == 0:
            container_ids = result.stdout.strip().splitlines()
            if container_ids:
                print(f"[*] Found {len(container_ids)} leftover stack container(s). Purging via compose down...")
                compose("down", "--remove-orphans", check=False)
                print("[✓] Stack cleanup complete.")

    except Exception as e:
        print(f"[!] Unexpected error during conflict check: {e}", file=sys.stderr)
        return False

    return True


def container_health(name: str) -> str:
    result = run("docker", "inspect", "--format", "{{.State.Health.Status}}", name, check=False)
    if result.returncode != 0:
        return "missing"
    return result.stdout.strip() or "none"


def wait_for_health(services: list[str], timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    pending = set(services)
    print(f"[*] Waiting for services {list(pending)} to report healthy (timeout: {timeout}s)...")
    
    while pending and time.monotonic() < deadline:
        for name in list(pending):
            status = container_health(name)
            if status == "healthy":
                print(f"  [✓] Service '{name}' is healthy")
                pending.discard(name)
            elif status in ("unhealthy", "missing"):
                print(f"  [!] Service '{name}' status: {status}", file=sys.stderr)
        if pending:
            time.sleep(3)
            
    if pending:
        print(f"[!] Timed out waiting for health checks on: {', '.join(sorted(pending))}", file=sys.stderr)
        return False
    return True


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def dump_container_logs(container_name: str, lines: int = 50):
    print(f"\n--- Diagnostic Logs for [{container_name}] (last {lines} lines) ---")
    res = run("docker", "logs", "--tail", str(lines), container_name, check=False)
    if res.stdout.strip():
        print(res.stdout)
    if res.stderr.strip():
        print(res.stderr, file=sys.stderr)
    print("-" * 60)


def ensure_fastapi_running(timeout: int) -> bool:
    print(f"[*] Polling FastAPI app on http://localhost:8000 (timeout: {timeout}s)...")
    deadline = time.monotonic() + timeout
    
    # Quick initial check
    while time.monotonic() < deadline:
        if http_ok("http://localhost:8000"):
            return True
        # Check if container died prematurely
        if run("docker", "inspect", "--format", "{{.State.Running}}", APP_CONTAINER, check=False).stdout.strip() != "true":
            print(f"[!] Container '{APP_CONTAINER}' stopped unexpectedly during startup.")
            dump_container_logs(APP_CONTAINER)
            return False
        time.sleep(2)

    print("[!] FastAPI not responding on :8000 — inspecting application logs and attempting manual restart...")
    dump_container_logs(APP_CONTAINER, lines=40)

    # Attempt to boot uvicorn manually inside container
    print(f"[*] Executing fallback startup command inside '{APP_CONTAINER}'...")
    exec_res = run(
        "docker", "exec", APP_CONTAINER, "bash", "-c",
        f"pkill -f uvicorn || true; cd {CONTAINER_WORKSPACE} && "
        "nohup uvicorn app:app --host 0.0.0.0 --port 8000 --log-level info "
        "> /tmp/fastapi.log 2>&1 &",
        check=False,
    )
    print(f"[*] Fallback execution return code: {exec_res.returncode}")

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if http_ok("http://localhost:8000"):
            print("[✓] FastAPI successfully recovered via fallback startup.")
            return True
        time.sleep(2)
        
    # Dump internal log file if it exists
    print("[!] Fallback failed. Checking /tmp/fastapi.log inside container:")
    log_res = run("docker", "exec", APP_CONTAINER, "cat", "/tmp/fastapi.log", check=False)
    if log_res.stdout.strip():
        print(log_res.stdout)
    else:
        dump_container_logs(APP_CONTAINER, lines=60)
        
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

    if not ensure_docker_running():
        return 1

    if not ensure_env_file():
        print("[!] Fill in .env with real secrets, then re-run this script.", file=sys.stderr)
        return 1

    if not check_and_cleanup_conflicts():
        print("[!] Container cleanup/conflict check failed.", file=sys.stderr)
        return 1

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    print("[*] Validating docker-compose.yml configuration...")
    validate = compose("config", "--quiet", check=False)
    if validate.returncode != 0:
        print(f"[!] Docker compose config validation failed:\n{validate.stderr.strip()}", file=sys.stderr)
        return 1

    up_args = ["up", "-d"]
    if args.build:
        up_args.append("--build")
    
    print(f"[*] Starting docker-compose stack: docker compose {' '.join(up_args)}")
    up = compose(*up_args, check=False)
    if up.stdout.strip():
        print(up.stdout.strip())
    
    if up.returncode != 0:
        print(f"[!] Failed to start docker-compose stack:\n{up.stderr.strip()}", file=sys.stderr)
        return 1

    if not wait_for_health(HEALTHY_SERVICES, args.timeout):
        print("[!] Warning: Some dependent services did not become fully healthy. Review output above.", file=sys.stderr)

    # Verify main dev container state
    run_status = run("docker", "inspect", "--format", "{{.State.Running}}", APP_CONTAINER, check=False)
    if run_status.returncode != 0 or run_status.stdout.strip() != "true":
        print(f"[!] Critical: Container '{APP_CONTAINER}' is not running.", file=sys.stderr)
        dump_container_logs(APP_CONTAINER)
        return 1

    if not ensure_fastapi_running(args.timeout):
        print(f"[!] Critical: FastAPI failed to serve requests.", file=sys.stderr)
        return 1
        
    print("[✓] FastAPI is responsive on port 8000.")

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
        print(f"  Tailscale    : http://{ts_ip}:8000  /  http://{ts_ip}:8443")
    else:
        print("  Tailscale    : not connected")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())