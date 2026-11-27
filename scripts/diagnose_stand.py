"""Read-only environment checks; no configuration values appear in output."""
import json
import os
import platform
from shutil import disk_usage
import socket
import subprocess
from pathlib import Path


def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return p.stdout.strip() if p.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def limit(name):
    path = Path("/sys/fs/cgroup") / name
    return path.read_text().strip() if path.is_file() else None


def main():
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
        loopback = True
    except OSError:
        loopback = False
    result = {
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "cgroup_cpu_max": limit("cpu.max"), "cgroup_memory_max": limit("memory.max"),
        "free_disk_bytes": disk_usage(".").free, "loopback_bind": loopback,
        "docker": command("docker", "--version"),
        "docker_server": command("docker", "version", "--format", "{{.Server.Version}}"),
        "compose": command("docker", "compose", "version", "--short"),
        "configured": {key: bool(os.getenv(key)) for key in
                       ("GIGACHAT_CREDENTIALS", "YANDEX_API_KEY", "DB_HOST",
                        "QDRANT_URL", "REDIS_HOST", "DIFY_BASE_URL")},
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
