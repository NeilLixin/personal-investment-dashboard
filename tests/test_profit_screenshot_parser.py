import pytest

from src.profit_screenshot_parser import (
    build_market_snapshot_from_profit_item, detect_profit_screenshot_source,
    match_profit_items_to_holdings, parse_profit_screenshot_text,
    recommend_profit_item_codes,
)


SAMPLE = """支付宝 今日收益
账户资产：12,000.00
当日收益：−120.50
2 只基金
日期：07-02
示例海外指数联接C
基金代码：001234
资产金额：4,000.00
涨跌幅：＋0.65%
最新值：1.2345
当日收益：+20.00
持有收益：+200.00
持有收益率：+5.00%
示例科技指数联接...
基金代码：005678
金额：¥8,000.00
涨跌幅：-1.75%
最新净值：2.3456
当日收益：－140.50
持有收益：￥300.00
持有收益率：＋3.90%"""


def test_detect_and_parse_profit_screenshot():
    assert detect_profit_screenshot_source(SAMPLE) == "alipay_profit"
    parsed = parse_profit_screenshot_text(SAMPLE)
    assert parsed["ok"] and parsed["account"]["total_assets"] == 12000
    assert parsed["account"]["daily_pnl"] == pytest.approx(-120.5)
    assert parsed["account"]["fund_count"] == 2 and parsed["account"]["snapshot_date"] == "07-02"
    assert [x["code"] for x in parsed["items"]] == ["001234", "005678"]
    assert parsed["items"][0]["change_pct"] == pytest.approx(.0065)
    assert parsed["items"][1]["daily_pnl"] == pytest.approx(-140.5)
    assert parsed["items"][1]["holding_return_pct"] == pytest.approx(.039)


def test_code_matches_even_when_name_is_truncated():
    items = parse_profit_screenshot_text(SAMPLE)["items"]
    holdings = [{"id":9,"code":"005678","name":"完整名称不同也按代码匹配","platform":"支付宝","asset_type":"海外资产"}]
    result = match_profit_items_to_holdings([items[1]], holdings)[0]
    assert result["holding_id"] == 9 and result["match_status"] == "已匹配"
    snapshot = build_market_snapshot_from_profit_item(result, holdings[0], "alipay_profit")
    assert snapshot["source"] == "screenshot" and snapshot["quality_level"] == "third_party_estimate"


def test_missing_fields_and_empty_text_are_graceful():
    empty = parse_profit_screenshot_text("")
    assert not empty["ok"] and empty["warnings"]
    partial = parse_profit_screenshot_text("天天基金\n示例产品\n001234")
    assert partial["ok"] and partial["warnings"]


def test_multiple_items_do_not_mix_columns():
    items = parse_profit_screenshot_text(SAMPLE)["items"]
    assert items[0]["daily_pnl"] == 20
    assert items[1]["daily_pnl"] == pytest.approx(-140.5)


def test_profit_name_can_recommend_code_but_never_auto_fill():
    candidates = [{"code":"000001", "short_name":"示例基金A"}]
    exact = recommend_profit_item_codes([{"name":"示例基金A", "code":""}], candidates)[0]
    assert exact["recommended_code"] == "000001" and exact["confirm_code_fill"] is False
    truncated = recommend_profit_item_codes([{"name":"示例基...", "code":""}], candidates)[0]
    assert truncated["confirm_code_fill"] is False
