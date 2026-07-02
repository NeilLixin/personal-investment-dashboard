from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fund_code_service import refresh_fund_code_candidates

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    result = refresh_fund_code_candidates(force=args.force)
    print("刷新状态:", result["status"]); print("候选总数:", result["total"]); print("各数据源:", result["counts"])
    print("失败接口:", result["failed_sources"]); print("错误:", result["errors"])
    raise SystemExit(0 if result["ok"] else 1)
