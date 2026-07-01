from src.eastmoney_parser import parse_eastmoney_holdings_from_ocr_items


def item(text, x, y, width=120, height=22):
    return {"text": text, "center_x": x, "center_y": y, "min_x": x-width/2, "max_x": x+width/2,
            "min_y": y-height/2, "max_y": y+height/2}


def example_items():
    rows = [
        ("A500基金", ["58,963.80", "41700", "1.414", "+4,700.18", "-291.90"], ["", "41700", "1.301", "+8.686%", "-0.493%"]),
        ("芯片ETF", ["35,202.60", "10600", "3.321", "+4,209.67", "-198.77"], ["", "4000", "2.924", "+13.577%", "-0.562%"]),
        ("通信ETF", ["27,488.00", "16000", "1.718", "-463.58", "-563.45"], ["", "6000", "1.747", "-1.660%", "-2.009%"]),
    ]
    values = [item("东方财富", 500, 30), item("买入", 100, 90), item("总资产", 120, 130), item("121,960.93", 120, 165),
              item("当日盈亏", 320, 130), item("-1,054.12", 320, 165), item("证券市值", 520, 130), item("121,654.40", 520, 165),
              item("持仓盈亏", 720, 130), item("+8,446.27", 720, 165), item("可用", 120, 195), item("306.43", 120, 225),
              item("可取", 320, 195), item("306.43", 320, 225), item("场内基金", 100, 280)]
    xs = [100, 300, 500, 700, 900]
    for row_index, (name, first, second) in enumerate(rows):
        y = 330 + row_index * 110; values.append(item(name, xs[0], y))
        for col in range(5):
            if first[col]: values.append(item(first[col], xs[col], y+30))
            if second[col]: values.append(item(second[col], xs[col], y+57))
    values.append(item("首页", 100, 760))
    return values


def test_parse_three_holdings_and_summary():
    result = parse_eastmoney_holdings_from_ocr_items(example_items(), 1000, 800)
    assert result["ok"] and len(result["holdings"]) == 3
    assert result["account_summary"] == {"total_asset": 121960.93, "today_profit": -1054.12,
        "security_market_value": 121654.40, "holding_profit": 8446.27, "available_cash": 306.43, "withdrawable_cash": 306.43}
    a500, chip, telecom = result["holdings"]
    assert (a500["current_value"], a500["holding_share"], a500["latest_price"], a500["cost_price"]) == (58963.8, 41700, 1.414, 1.301)
    assert (a500["profit_amount"], a500["profit_rate"], a500["today_profit"], a500["today_profit_rate"]) == (4700.18, 8.686, -291.9, -0.493)
    assert chip["available_share"] == 4000 and chip["asset_type"] == "A股科技/半导体/通信"
    assert telecom["profit_amount"] == -463.58 and telecom["today_profit"] == -563.45


def test_empty_and_unordered_items_are_safe():
    assert not parse_eastmoney_holdings_from_ocr_items([])["ok"]
    result = parse_eastmoney_holdings_from_ocr_items(list(reversed(example_items())), 1000, 800)
    assert result["ok"] and [x["name"] for x in result["holdings"]] == ["A500基金", "芯片ETF", "通信ETF"]
