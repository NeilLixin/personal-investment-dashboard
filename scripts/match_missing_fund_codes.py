from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import fetch_all
from src.fund_code_service import apply_confirmed_code_matches, batch_match_missing_holding_codes

parser = argparse.ArgumentParser(description="预览缺失基金代码的保守匹配结果")
parser.add_argument("--apply-exact", action="store_true", help="写入完全匹配项；仍建议先在页面人工确认")
args = parser.parse_args()
result = batch_match_missing_holding_codes(fetch_all("holdings"))
for item in result["items"]:
    print({key:item.get(key) for key in ("holding_id","holding_name","recommended_code","recommended_name","confidence","status","reason")})
if args.apply_exact:
    confirmations = [{**item, "confirmed":item["status"] == "exact"} for item in result["items"]]
    print(apply_confirmed_code_matches(confirmations))
