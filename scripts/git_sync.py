from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, check=False)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return result


def main() -> int:
    if run_git("rev-parse", "--is-inside-work-tree").returncode:
        print("当前目录还不是 Git 仓库，请先执行 README 中的 git init 步骤。")
        return 1
    if run_git("remote", "get-url", "origin").returncode:
        print("未配置 remote origin，请先执行：git remote add origin <你的GitHub仓库地址>")
        return 1
    print("当前状态：")
    run_git("status", "--short", "--branch")
    if run_git("add", ".").returncode:
        return 1
    staged = run_git("diff", "--cached", "--quiet")
    if staged.returncode == 1:
        message = " ".join(sys.argv[1:]).strip() or f"update dashboard: {datetime.now():%Y-%m-%d %H:%M:%S}"
        if run_git("commit", "-m", message).returncode:
            return 1
    else:
        print("没有需要提交的改动。")
    if run_git("push").returncode:
        print("推送失败。若确实需要代理，只配置当前仓库：")
        print("git config --local http.proxy http://127.0.0.1:7897")
        print("git config --local https.proxy http://127.0.0.1:7897")
        return 1
    print("同步完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
