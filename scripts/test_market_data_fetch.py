from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database import fetch_all
from src.market_data_service import (
    fetch_quote_for_holding, get_market_provider_status, holding_code,
    infer_market_instrument_type, save_market_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断 AKShare 市场数据，不默认写数据库。")
    parser.add_argument("--codes", nargs="*", default=[])
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()
    holdings = fetch_all("holdings")
    codes = args.codes or [holding_code(row) for row in holdings if holding_code(row)]
    print("Python:", sys.executable)
    provider = get_market_provider_status(); print("AKShare:", provider)
    print("测试代码:", codes or "没有可测试的 6 位代码，请使用 --codes")
    by_code = {holding_code(row): row for row in holdings if holding_code(row)}
    for code in codes:
        holding = by_code.get(code, {"id":None,"code":code,"name":"诊断代码","platform":"手动","asset_type":""})
        inferred = infer_market_instrument_type(holding); print("\n", code, "=>", inferred["instrument_type"])
        result = fetch_quote_for_holding(holding)
        public = {key:value for key,value in result.items() if key != "raw_payload"}
        print("调用:", result.get("instrument_type"), "结果:", public)
        if args.write_db and result.get("ok"):
            if not holding.get("id"):
                print("未写入：本地 holdings 没有匹配该代码")
            else:
                snapshot_id = save_market_snapshot({**holding, **result, "holding_id":holding["id"], "source":"market_api", "snapshot_date":date.today().isoformat()})
                print("已写入 market_snapshots，id:", snapshot_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
