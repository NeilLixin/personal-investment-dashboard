from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database import init_db  # noqa: E402
from src.export_service import backup_database, export_all_csv_zip  # noqa: E402


if __name__ == "__main__":
    init_db()
    print(f"SQLite 备份：{backup_database()}")
    print(f"CSV 压缩包：{export_all_csv_zip()}")
