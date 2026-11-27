"""Prepare pinned upstream Dify and start the pilot with external storage."""
import argparse
from pathlib import Path
import os
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "infra/dify"
LOCAL = ROOT / "data/stand"
PIN = "ec871819e46de82f2f9ee33a71a61d96a58bdb37"
SERVICES = "api worker worker_beat web plugin_daemon sandbox ssrf_proxy nginx".split()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "check", "start"))
    action = parser.parse_args().action
    LOCAL.mkdir(parents=True, exist_ok=True)
    upstream = LOCAL / "upstream"
    envfile = LOCAL / ".env"
    if action == "prepare":
        if not upstream.exists():
            subprocess.run(["git", "clone", "--depth=1", "--branch", "1.9.2",
                            "https://github.com/langgenius/dify.git", str(upstream)], check=True)
        if not envfile.exists():
            with open(os.open(envfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
                out.write((KIT / "stand.env.example").read_text())
                sandbox_key = secrets.token_hex(32)
                for key in ("SECRET_KEY", "PLUGIN_DAEMON_KEY", "PLUGIN_DIFY_INNER_API_KEY",
                            "SANDBOX_API_KEY", "CODE_EXECUTION_API_KEY"):
                    value = sandbox_key if "SANDBOX" in key or "EXECUTION" in key else secrets.token_hex(32)
                    print(f"{key}={value}", file=out)
    rev = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if rev != PIN:
        raise SystemExit("Unexpected Dify revision")
    if action == "prepare":
        print("Prepared data/stand/.env; configure approved external services.")
        return
    docker = upstream / "docker"
    cmd = ["docker", "compose", "-p", "rag-pilot", "--env-file", str(envfile),
           "-f", str(docker / "docker-compose.yaml"), "-f", str(KIT / "compose.pilot.yaml")]
    import json
    model = json.loads(subprocess.check_output(cmd + ["config", "--format", "json"]))
    config = model["services"]["api"]["environment"]
    if set(model["services"]) != set(SERVICES):
        raise SystemExit("Unexpected Compose services or active profiles")
    if action == "check":
        print("Compose validated; only application services enabled.")
        return
    required = ("DB_HOST", "DB_PASSWORD", "DB_USERNAME", "REDIS_HOST", "REDIS_PASSWORD",
                "CELERY_BROKER_URL", "QDRANT_URL", "QDRANT_API_KEY")
    resolved = subprocess.check_output(cmd + ["config", "--environment"], text=True)
    supplied = dict(line.split("=", 1) for line in resolved.splitlines() if "=" in line)
    if any(not supplied.get(key) for key in required) or config["VECTOR_STORE"] != "qdrant":
        raise SystemExit("Configure approved Postgres Pro, cache and Platform V first")
    subprocess.run(cmd + ["up", "-d", *SERVICES], check=True)


if __name__ == "__main__":
    main()
