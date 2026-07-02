from streamlit.testing.v1 import AppTest


def test_market_snapshot_pages_render_without_snapshots():
    for page in ("总览", "投资日报", "风险雷达"):
        app = AppTest.from_file("app.py", default_timeout=15).run()
        app.radio[0].set_value(page).run()
        assert not app.exception


def test_dashboard_shows_refresh_diagnostic_after_all_skipped():
    app = AppTest.from_file("app.py", default_timeout=15).run()
    app.session_state["market_refresh_result"] = {
        "provider":"akshare","success_count":0,"failed_count":0,"skipped_count":1,
        "success_items":[],"failed_items":[],"skipped_items":[{"reason":"无基金代码"}],"error":None,
    }
    app.run()
    assert any("查看高级诊断" in item.value for item in app.warning)
