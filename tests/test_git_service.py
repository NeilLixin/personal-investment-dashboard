from pathlib import Path

from src.git_service import get_git_status


def test_git_status_without_repository(tmp_path: Path) -> None:
    status = get_git_status(tmp_path)
    assert status["branch"] == "未知" and status["remote"] == "未配置" and status["dirty"] is False
