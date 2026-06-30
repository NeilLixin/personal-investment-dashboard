from __future__ import annotations

import subprocess
from pathlib import Path

from src.config import BASE_DIR


def get_git_status(repo: Path = BASE_DIR) -> dict:
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return {"branch": run("branch", "--show-current") or "未知", "remote": run("remote", "get-url", "origin") or "未配置",
            "dirty": bool(run("status", "--porcelain"))}
