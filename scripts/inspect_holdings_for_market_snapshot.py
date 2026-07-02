from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database import fetch_all
from src.market_data_service import holding_code, holding_name, infer_market_instrument_type
from src.fund_code_service import load_fund_code_candidates, match_fund_code_by_name


def main() -> int:
    rows = fetch_all("holdings"); inferred = [infer_market_instrument_type(row) for row in rows]; candidates = load_fund_code_candidates()
    counts = Counter(item["instrument_type"] for item in inferred)
    print("holdings 总数:", len(rows)); print("有 code:", sum(bool(holding_code(row)) for row in rows)); print("无 code:", sum(not holding_code(row) for row in rows))
    for key in ("open_fund","exchange_etf","gold","cash","manual","unknown"): print(f"{key}:", counts[key])
    print("\n逐条诊断:")
    for row, info in zip(rows, inferred):
        recommendation = match_fund_code_by_name(holding_name(row), candidates) if not holding_code(row) else {}
        print({"id":row.get("id"),"code":holding_code(row),"name":holding_name(row),"platform":row.get("platform"),
               "asset_type":row.get("asset_type"),"inferred_type":info["instrument_type"],"can_attempt_api":info["can_attempt_api"],"reason":info["reason"],
               "recommendation":recommendation.get("best"), "match_status":recommendation.get("status")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
