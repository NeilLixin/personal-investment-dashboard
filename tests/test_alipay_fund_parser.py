import random

import pytest

from src.alipay_fund_parser import parse_alipay_fund_holdings_from_ocr_items
from src.import_service import parsed_to_drafts


def _item(text: str, x: float, y: float) -> dict:
    return {
        "text": text,
        "score": 0.99,
        "box": [[x - 40, y - 12], [x + 40, y - 12], [x + 40, y + 12], [x - 40, y + 12]],
        "center_x": x,
        "center_y": y,
        "min_x": x - 40,
        "max_x": x + 40,
        "min_y": y - 12,
        "max_y": y + 12,
    }


def _sample_items() -> list[dict]:
    rows = [
        ("华安汇宏精选混合C", None, 100, "10,788.47", "+8.47", "+1,872.77", "+21.01%"),
        ("天弘中证电网设备主题指数C", None, 300, "6,988.18", "-77.37", "+193.54", "+2.85%"),
        ("天弘标普500(QDII-FOF)A", None, 520, "6,110.53", "-36.58", "+257.32", "+4.40%"),
        ("华夏全球科技先锋混合", "(QDII)C", 760, "3,500.00", "0.00", "0.00", "0.00%"),
        ("易方达全球成长精选混合", "(QDII)A", 1010, "2,812.65", "-141.53", "+802.65", "+40.33%"),
        ("财通成长优选混合C", None, 1280, "1,804.91", "-51.34", "+4.91", "+0.29%"),
    ]
    items: list[dict] = []
    for name, continuation, y, current, yesterday, profit, rate in rows:
        items.extend([
            _item(name, 100, y),
            _item(current, 550, y),
            _item(yesterday, 550, y + 42),
            _item(profit, 850, y),
            _item(rate, 850, y + 42),
        ])
        if continuation:
            items.append(_item(continuation, 100, y + 42))
    items.extend([
        _item("市场解读 美股七姐妹被笑成老登股", 260, 650),
        _item("产品提醒 本产品重要公告", 260, 1180),
        _item("基金市场", 120, 1510),
        _item("机会", 380, 1510),
        _item("自选", 620, 1510),
        _item("持有", 850, 1510),
    ])
    return items


def test_parse_six_alipay_fund_holdings_from_three_columns() -> None:
    result = parse_alipay_fund_holdings_from_ocr_items(_sample_items(), image_width=1000)
    assert result["ok"] is True
    holdings = result["holdings"]
    assert len(holdings) == 6
    expected = [
        ("华安汇宏精选混合C", 10788.47, 8.47, 1872.77, 21.01),
        ("天弘中证电网设备主题指数C", 6988.18, -77.37, 193.54, 2.85),
        ("天弘标普500(QDII-FOF)A", 6110.53, -36.58, 257.32, 4.40),
        ("华夏全球科技先锋混合(QDII)C", 3500.00, 0.00, 0.00, 0.00),
        ("易方达全球成长精选混合(QDII)A", 2812.65, -141.53, 802.65, 40.33),
        ("财通成长优选混合C", 1804.91, -51.34, 4.91, 0.29),
    ]
    for holding, values in zip(holdings, expected):
        name, current, yesterday, profit, rate = values
        assert holding["name"] == name
        assert holding["current_value"] == pytest.approx(current)
        assert holding["yesterday_profit"] == pytest.approx(yesterday)
        assert holding["profit_amount"] == pytest.approx(profit)
        assert holding["profit_rate"] == pytest.approx(rate)
        assert holding["cost_amount"] == pytest.approx(current - profit)


def test_ads_and_bottom_navigation_are_ignored() -> None:
    result = parse_alipay_fund_holdings_from_ocr_items(_sample_items(), image_width=1000)
    ignored = result["debug"]["ignored_items"]
    assert any(text.startswith("市场解读") for text in ignored)
    assert any(text.startswith("产品提醒") for text in ignored)
    assert {"基金市场", "机会", "自选", "持有"}.issubset(set(ignored))


def test_empty_items_are_failure_safe() -> None:
    result = parse_alipay_fund_holdings_from_ocr_items([])
    assert result["ok"] is False
    assert result["holdings"] == []
    assert result["debug"]["item_count"] == 0


def test_unordered_items_are_sorted_before_parsing() -> None:
    items = _sample_items()
    random.Random(7).shuffle(items)
    result = parse_alipay_fund_holdings_from_ocr_items(items, image_width=1000)
    assert [item["name"] for item in result["holdings"]] == [
        "华安汇宏精选混合C",
        "天弘中证电网设备主题指数C",
        "天弘标普500(QDII-FOF)A",
        "华夏全球科技先锋混合(QDII)C",
        "易方达全球成长精选混合(QDII)A",
        "财通成长优选混合C",
    ]


def test_confirmation_draft_converts_displayed_percent_to_ratio() -> None:
    parsed = parse_alipay_fund_holdings_from_ocr_items(_sample_items(), image_width=1000)["holdings"]
    draft = parsed_to_drafts(parsed)
    assert draft.iloc[0]["profit_rate"] == pytest.approx(0.2101)
    assert draft.iloc[0]["yesterday_profit"] == pytest.approx(8.47)
