from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database import clear_tables, init_db  # noqa: E402
from src.sample_data import seed_demo_data  # noqa: E402


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        raise SystemExit("该操作会清空本地数据。确认后请执行：python scripts/reset_demo_data.py --yes")
    init_db()
    clear_tables(["holdings", "trades", "plans", "rules", "ocr_import_batches", "app_settings"])
    seed_demo_data(skip_if_holdings_exist=False)
    print("数据库已重置为 Demo 数据。")
