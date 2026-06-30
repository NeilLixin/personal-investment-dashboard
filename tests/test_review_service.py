from src.review_service import generate_review_insights, get_mistake_tag_stats, get_review_summary


def test_empty_review_stats() -> None:
    assert get_review_summary([])["total_trades"] == 0
    assert generate_review_insights([])


def test_pending_planned_impulsive_and_tags() -> None:
    rows = [
        {"trade_date":"2026-01-01", "review_date":"2026-01-02", "is_planned":1, "review_status":"done", "result_type":"盈利", "mistake_tags":"[]"},
        {"trade_date":"2026-01-03", "review_date":"2026-01-04", "is_planned":0, "review_status":"pending", "result_type":"未判断", "mistake_tags":"[\"追涨\"]"},
    ]
    summary = get_review_summary(rows)
    assert summary["pending_count"] == 1 and summary["planned_count"] == 1 and summary["impulsive_count"] == 1
    assert get_mistake_tag_stats(rows)[0] == {"tag":"追涨", "count":1}
