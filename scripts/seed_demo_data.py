from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database import init_db  # noqa: E402
from src.sample_data import seed_demo_data  # noqa: E402


if __name__ == "__main__":
    init_db()
    seed_demo_data()
    print("Demo 数据初始化完成。已有持仓时不会重复写入。")
