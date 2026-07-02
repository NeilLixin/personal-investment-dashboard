from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "investment_dashboard.db"
UPLOADS_DIR = DATA_DIR / "uploads"
BACKUPS_DIR = DATA_DIR / "backups"
EXPORTS_DIR = DATA_DIR / "exports"
SYNC_DIR = DATA_DIR / "sync"
SYNC_FILE = SYNC_DIR / "portfolio_sync.json"
APP_VERSION = "0.7.0"

ASSET_TYPES = [
    "现金",
    "A股宽基",
    "A股科技/半导体/通信",
    "海外资产",
    "黄金",
    "债券/固收",
    "其他",
]
MARKETS = ["A股", "海外", "美股", "黄金", "现金", "其他"]
PLATFORMS = ["支付宝", "东方财富", "券商", "招商银行", "浙商银行", "京东金融", "手动", "其他"]
RISK_LEVELS = ["低", "中", "高"]
TRADE_ACTIONS = ["买入", "卖出", "定投", "减仓", "补仓", "观察"]
EMOTIONS = ["冷静", "恐慌", "怕踏空", "冲动", "按计划"]
PLAN_TYPES = ["补仓", "减仓", "止盈", "止损", "定投", "观察"]


def ensure_directories() -> None:
    for path in (DATA_DIR, UPLOADS_DIR, BACKUPS_DIR, EXPORTS_DIR, SYNC_DIR):
        path.mkdir(parents=True, exist_ok=True)
