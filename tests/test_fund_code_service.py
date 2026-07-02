import pandas as pd

from src.database import fetch_all, init_db, insert_row
from src.fund_code_service import (
    apply_confirmed_code_matches, batch_match_missing_holding_codes, match_fund_code_by_name,
    normalize_fund_code, normalize_fund_name, refresh_fund_code_candidates, validate_fund_code,
)


def candidates():
    return [
        {"code":"000001", "short_name":"示例成长混合A", "full_name":"示例成长混合A", "fund_type":"混合型"},
        {"code":"000002", "short_name":"示例成长混合C", "full_name":"示例成长混合C", "fund_type":"混合型"},
        {"code":"510300", "short_name":"沪深300ETF", "full_name":"沪深300ETF", "fund_type":"ETF"},
    ]


def test_normalize_and_validate_code_and_name():
    assert normalize_fund_code("代码 000001") == "000001"
    assert normalize_fund_code(1.0) == "000001"
    assert validate_fund_code("abc")["ok"] is False
    assert normalize_fund_name(" 示例成长混合 C（QDII） ").endswith("C(QDII)")


def test_exact_and_ac_ambiguity_are_conservative():
    exact = match_fund_code_by_name("示例成长混合A", candidates())
    assert exact["status"] == "exact" and exact["best"]["code"] == "000001"
    ambiguous = match_fund_code_by_name("示例成长混合", candidates())
    assert ambiguous["status"] == "multiple_candidates"


def test_short_or_truncated_name_is_not_auto_selected():
    result = match_fund_code_by_name("示例成...", candidates())
    assert result["status"] in {"low_confidence", "multiple_candidates", "no_match"}


def test_etf_and_etf_link_are_not_mixed():
    rows = [{"code":"510300", "short_name":"沪深300ETF"}, {"code":"000300", "short_name":"沪深300ETF联接A"}]
    result = match_fund_code_by_name("沪深300ETF联接A", rows)
    assert result["best"]["code"] == "000300"


def test_refresh_isolated_sources_and_daily_cache(tmp_path):
    class FakeAK:
        def fund_purchase_em(self): return pd.DataFrame([{"基金代码":"000001", "基金简称":"示例成长混合A", "基金类型":"混合型"}])
        def fund_info_index_em(self, **kwargs): raise RuntimeError("temporary")
        def fund_etf_spot_em(self): return pd.DataFrame([{"代码":"510300", "名称":"沪深300ETF"}])
    db = tmp_path / "codes.db"
    first = refresh_fund_code_candidates(True, db, FakeAK())
    assert first["ok"] and first["status"] == "partial" and first["total"] == 2
    cached = refresh_fund_code_candidates(False, db, FakeAK())
    assert cached["status"] == "cached"


def test_batch_and_confirmed_write_protect_conflicts(tmp_path):
    db = tmp_path / "codes.db"; init_db(db)
    holding_id = insert_row("holdings", {"name":"示例成长混合A", "platform":"支付宝", "asset_type":"基金", "market":"A股"}, db)
    batch = batch_match_missing_holding_codes(fetch_all("holdings", db), candidates(), db)
    assert batch["exact_count"] == 1
    saved = apply_confirmed_code_matches([{**batch["items"][0], "confirmed":True}], db)
    assert saved["updated"] == 1 and fetch_all("holdings", db)[0]["code"] == "000001"
    conflict = apply_confirmed_code_matches([{"holding_id":holding_id, "recommended_code":"000002", "confirmed":True}], db)
    assert conflict["conflicts"] == 1 and fetch_all("holdings", db)[0]["code"] == "000001"
