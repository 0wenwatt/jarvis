#!/usr/bin/env python3
"""Stage, secret-scan, commit, and push the jarvis-dev workspace to git.

Usage:
    python development/scripts/push_to_git.py [-m "message"] [--branch BRANCH]
        [--remote origin] [--dry-run] [--yes]

Safety:
    - Refuses to stage any path that looks like a real secrets file (.env,
      .env.<anything>, *.pem, *.key, id_rsa*, ...) even though .gitignore
      should already exclude them — this is a second, independent guard.
    - Scans the actual staged diff content for secret-shaped strings (cloud
      API keys, PATs, private key blocks, generic "key = <long token>"
      assignments) and aborts the commit if any are found.
    - Never pushes without an explicit --yes flag or interactive confirmation.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Paths that must never be committed, even if untracked/force-added by mistake.
BLOCKED_PATH_PATTERNS = [
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\.(?!example$|template$)[^/]+$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"(^|/)id_rsa[^/]*$"),
    re.compile(r"\.pfx$"),
    re.compile(r"\.p12$"),
]

# Content patterns that indicate a real secret leaked into a diff.
SECRET_PATTERNS = [
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained PAT"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "Anthropic API key"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style API key"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API key"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "Groq API key"),
    (re.compile(r"tskey-auth-[A-Za-z0-9-]{10,}"), "Tailscale auth key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PGP|PRIVATE) PRIVATE KEY-----"), "Private key block"),
    (
        re.compile(r"(?i)(secret|password|passwd|token|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/_\-]{16,}"),
        "Generic secret-looking assignment",
    ),
]


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def find_blocked_paths(staged_files: list[str]) -> list[str]:
    return [f for f in staged_files if any(p.search(f) for p in BLOCKED_PATH_PATTERNS)]


def scan_staged_diff() -> list[str]:
    """Return a list of human-readable findings for any secret-shaped content."""
    diff = run_git("diff", "--cached", "-U0").stdout
    findings = []
    for pattern, label in SECRET_PATTERNS:
        for match in pattern.finditer(diff):
            snippet = match.group(0)
            redacted = snippet[:8] + "..." if len(snippet) > 8 else "***"
            findings.append(f"{label}: {redacted}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--message", default="Update jarvis-dev workspace", help="Commit message")
    parser.add_argument("--branch", default=None, help="Branch to push (default: current branch)")
    parser.add_argument("--remote", default="origin", help="Remote to push to (default: origin)")
    parser.add_argument("--dry-run", action="store_true", help="Stage and scan only; do not commit or push")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive push confirmation")
    args = parser.parse_args()

    if run_git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        print(f"[!] {REPO_ROOT} is not a git repository", file=sys.stderr)
        return 1

    print("[*] Staging changes (git add -A)...")
    run_git("add", "-A")

    staged = run_git("diff", "--cached", "--name-only").stdout.splitlines()
    if not staged:
        print("[*] Nothing to commit — working tree matches HEAD.")
        return 0

    blocked = find_blocked_paths(staged)
    if blocked:
        run_git("reset", check=False)
        print("[!] Refusing to commit — secret-like paths were staged:", file=sys.stderr)
        for path in blocked:
            print(f"    - {path}", file=sys.stderr)
        print("    Fix your .gitignore, then re-run this script.", file=sys.stderr)
        return 1

    findings = scan_staged_diff()
    if findings:
        run_git("reset", check=False)
        print("[!] Refusing to commit — possible secrets found in the staged diff:", file=sys.stderr)
        for finding in findings:
            print(f"    - {finding}", file=sys.stderr)
        return 1

    print(f"[✓] {len(staged)} file(s) staged, no secrets detected.")
    for path in staged:
        print(f"    - {path}")

    if args.dry_run:
        print("[*] --dry-run set; leaving changes staged but uncommitted.")
        return 0

    run_git("commit", "-m", args.message)
    print(f"[✓] Committed: {args.message}")

    branch = args.branch or run_git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    if not args.yes:
        reply = input(f"Push to {args.remote}/{branch}? [y/N] ").strip().lower()
        if reply != "y":
            print("[*] Push skipped. Commit is local only.")
            return 0

    print(f"[*] Pushing to {args.remote}/{branch}...")
    push = run_git("push", args.remote, branch, check=False)
    print(push.stdout)
    if push.returncode != 0:
        print(push.stderr, file=sys.stderr)
        print("[!] Push failed.", file=sys.stderr)
        return 1

    print("[✓] Push complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
