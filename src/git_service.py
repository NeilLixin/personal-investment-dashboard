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


def run_git_action(action: str, message: str = "sync portfolio snapshot", repo: Path = BASE_DIR) -> dict:
    """Run the two explicit Git actions exposed by the sync page; never stores credentials."""
    commands = [["git", "pull"]] if action == "pull" else [["git", "add", "data/sync/portfolio_sync.json"], ["git", "commit", "-m", message], ["git", "push"]]
    output = []
    try:
        for command in commands:
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=60)
            output.append((result.stdout or result.stderr).strip())
            if result.returncode and not (action == "push" and command[1] == "commit" and "nothing to commit" in output[-1]):
                return {"ok": False, "message": output[-1] or "Git 命令执行失败"}
        return {"ok": True, "message": "\n".join(filter(None, output)) or "操作完成"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": str(exc)}
