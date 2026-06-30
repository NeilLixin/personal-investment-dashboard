import pytest

from src.alipay_parser import parse_alipay_text


def test_parse_alipay_fund() -> None:
    text = """产品名称：中证A500指数基金
基金代码：159xxx
持有金额：12,345.67
持有收益：+345.67
收益率：+2.88%
昨日收益：12.30
持有份额：10,000.00
最新净值：1.2345"""
    result = parse_alipay_text(text)[0]
    assert result["name"] == "中证A500指数基金"
    assert result["current_value"] == pytest.approx(12345.67)
    assert result["profit_amount"] == pytest.approx(345.67)
    assert result["profit_rate"] == pytest.approx(0.0288)
    assert result["asset_type"] == "A股宽基"


def test_parse_alipay_gold() -> None:
    text = """产品名称 支付宝黄金
持有金额 8,888.00
持有收益 -112.00
收益率 -1.24%
黄金克数 15.50
最新金价 573.42"""
    result = parse_alipay_text(text)[0]
    assert result["asset_type"] == "黄金"
    assert result["holding_share"] == pytest.approx(15.5)
    assert result["latest_price"] == pytest.approx(573.42)


def test_parse_multiple_products() -> None:
    text = """产品名称：纳斯达克100
持有金额：20,000
持有收益：2,000
收益率：11.11%
产品名称：稳健债券理财
持有金额：10,000
持有收益：100
收益率：1.01%"""
    results = parse_alipay_text(text)
    assert len(results) == 2
    assert results[0]["asset_type"] == "海外资产"
    assert results[1]["asset_type"] == "债券/固收"


def test_incomplete_ocr_text_uses_nearby_name_fallback() -> None:
    text = """我的资产
中证A500指数基金
持有金额
6,666.00
部分文字识别不完整"""
    result = parse_alipay_text(text)
    assert len(result) == 1
    assert result[0]["name"] == "中证A500指数基金"
    assert result[0]["current_value"] == pytest.approx(6666.0)
