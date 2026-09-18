"""🐳 AGENT 4: DevOps & Security Inspector.

Audits Dockerfile, docker-compose.yml, secret scan, and Docker runtime.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

failures: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append({"agent": "DevOps", "name": name, "detail": detail})


def check_file_contains(path: Path, pattern: str, name: str) -> None:
    if not path.exists():
        record(f"{name}_exists", False, f"missing {path}")
        return
    matched = bool(re.search(pattern, path.read_text(), re.MULTILINE))
    detail = "" if matched else f"pattern {pattern!r} not found in {path.name}"
    record(f"{name}_present", matched, detail)


def scan_for_secrets() -> None:
    """Strict regex scan for any real-looking secret in the working tree."""
    secret_patterns = [
        (r"sk-[A-Za-z0-9_-]{20,}", "openai/groq/openrouter key"),
        (r"gsk_[A-Za-z0-9_-]{20,}", "groq key"),
        (r"sk_live_[A-Za-z0-9]{20,}", "stripe live key"),
        (r"sk_test_[A-Za-z0-9]{20,}", "stripe test key"),
        (r"ghp_[A-Za-z0-9]{20,}", "github token"),
        (r"github_pat_[A-Za-z0-9_]{20,}", "github fine-grained"),
        (r"xox[bp]-[A-Za-z0-9-]{20,}", "slack token"),
        (r"AKIA[0-9A-Z]{16}", "aws access key"),
        (r"AIza[0-9A-Za-z_-]{35}", "google api key"),
    ]
    skip_dirs = {"__pycache__", ".git", ".venv", "node_modules", "audit_logs"}
    found_any = False
    for dp, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            full = Path(dp) / f
            # Skip the test_security.py fixture string (intentional test)
            if str(full).endswith("test_security.py"):
                continue
            # Skip JSON input files
            if "BUP_CSE_FEST" in f:
                continue
            try:
                text = full.read_text(errors="ignore")
            except Exception:
                continue
            for pat, label in secret_patterns:
                if re.search(pat, text):
                    found_any = True
                    record(f"secret_{label}", False, f"in {full}")
    if not found_any:
        record("no_secrets_in_tree", True)


def scan_image_for_secrets() -> None:
    """Verify the Docker image contains no env vars with secret values."""
    try:
        out = subprocess.run(
            ["docker", "inspect", "gridwise-api:latest"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        record("docker_inspect_runs", False, str(e))
        return
    if out.returncode != 0:
        record("docker_inspect_ok", False, out.stderr[:200])
        return
    record("docker_inspect_ok", True)
    info = json.loads(out.stdout)
    env = info[0]["Config"]["Env"]
    # GROQ_API_KEY should NOT be baked in
    for kv in env:
        if kv.startswith("GROQ_API_KEY=") and len(kv.split("=", 1)[1]) > 5:
            record("no_baked_api_key", False, kv)
            return
    record("no_baked_api_key", True)


def docker_healthcheck() -> None:
    """Verify the running container becomes healthy and /health works."""
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=ROOT,
        )
    except Exception as e:
        record("docker_ps_runs", False, str(e))
        return
    if "healthy" not in out.stdout:
        record("container_healthy", False, "no healthy container")
        return
    record("container_healthy", True)

    # curl /health
    try:
        import urllib.request

        r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)
        body = r.read().decode()
        if r.status == 200 and body == '{"status":"ok"}':
            record("health_endpoint_200", True)
        else:
            record("health_endpoint_200", False, f"{r.status} {body}")
    except Exception as e:
        record("health_endpoint_200", False, str(e))


def dockerfile_audit() -> None:
    df = ROOT / "Dockerfile"
    check_file_contains(df, r"^FROM\s+python:3.12-slim", "dockerfile_python312")
    check_file_contains(df, r"^USER\s+gridwise", "dockerfile_nonroot")
    check_file_contains(df, r"^EXPOSE\s+8000", "dockerfile_expose")
    check_file_contains(df, r"0\.0\.0\.0", "dockerfile_bind_all")
    check_file_contains(df, r"HEALTHCHECK", "dockerfile_healthcheck")
    # Should NOT copy .env
    if re.search(r"^COPY\s+\.env", df.read_text(), re.MULTILINE):
        record("dockerfile_no_env_copy", False, "copies .env")
    else:
        record("dockerfile_no_env_copy", True)


def compose_audit() -> None:
    cf = ROOT / "docker-compose.yml"
    text = cf.read_text()
    check_file_contains(cf, r"image:\s*gridwise-api", "compose_image")
    check_file_contains(cf, r'"8000:8000"', "compose_port_mapping")
    check_file_contains(cf, r"healthcheck:", "compose_healthcheck")
    check_file_contains(cf, r"restart:\s*unless-stopped", "compose_restart")
    check_file_contains(cf, r"0\.0\.0\.0", "compose_bind_all")


def dockerignore_audit() -> None:
    di = ROOT / ".dockerignore"
    text = di.read_text() if di.exists() else ""
    required = [".git", ".env", "__pycache__", "tests", "docs"]
    missing = [p for p in required if p not in text]
    if missing:
        record("dockerignore_comprehensive", False, f"missing {missing}")
    else:
        record("dockerignore_comprehensive", True)


def gitignore_audit() -> None:
    gi = ROOT / ".gitignore"
    text = gi.read_text() if gi.exists() else ""
    required = [".env", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"]
    missing = [p for p in required if p not in text]
    if missing:
        record("gitignore_comprehensive", False, f"missing {missing}")
    else:
        record("gitignore_comprehensive", True)


def docker_up_and_smoke() -> None:
    """Rebuild + restart + smoke test."""
    print("\n  [rebuilding image ...]")
    out = subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
    )
    if out.returncode != 0:
        record("docker_build_up", False, out.stderr[-300:])
        return
    record("docker_build_up", True)
    # Wait for healthcheck
    for i in range(15):
        time.sleep(2)
        ps = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=ROOT,
        )
        if "healthy" in ps.stdout:
            record("container_reaches_healthy", True)
            return
    record("container_reaches_healthy", False, "not healthy after 30s")


def main():
    print("=" * 60)
    print("🐳  AGENT 4: DEVOPS & SECURITY INSPECTOR")
    print("=" * 60)
    print()
    print("[4.1] Dockerfile / compose / ignore audits:")
    dockerfile_audit()
    compose_audit()
    dockerignore_audit()
    gitignore_audit()

    print("\n[4.2] Secret scan in working tree:")
    scan_for_secrets()

    print("\n[4.3] Docker image runtime audit:")
    scan_image_for_secrets()
    docker_healthcheck()

    print("\n[4.4] Docker rebuild + healthcheck (may take a minute):")
    docker_up_and_smoke()

    out = ROOT / "audit_logs" / "devops_failures.json"
    out.write_text(json.dumps({"agent": "DevOps", "failures": failures}, indent=2))
    print()
    print(f"DevOps total failures: {len(failures)}")
    if failures:
        for f in failures:
            print(f"  - {f['name']}: {f['detail']}")
    print(f"Wrote {out}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
