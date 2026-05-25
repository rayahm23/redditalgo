from scanner.report import (
    format_analyst_target,
    format_narrative,
    get_general_signals,
    get_small_stock_signals,
    render_results_html,
)


def _row(ticker: str, score: float, price: float | None) -> dict:
    return {
        "ticker": ticker,
        "final_score": score,
        "latest_price": price,
        "recommendation_type": "Watchlist",
        "signal_confidence_label": "MEDIUM",
        "risk_flag": "medium",
        "summary": f"{ticker} summary",
        "primary_narrative": f"Discussion on {ticker}.",
        "bullish_themes": ["earnings optimism"],
        "bearish_themes": [],
        "generated_at": "2026-05-24T20:00:00+00:00",
    }


def test_get_general_signals_top_ten_by_score():
    rows = [_row("AAA", 90, 200), _row("BBB", 80, 12), _row("CCC", 70, 8)]
    general = get_general_signals(rows, limit=2)
    assert [item["ticker"] for item in general] == ["AAA", "BBB"]
    assert general[0]["rank"] == 1


def test_get_small_stock_signals_filters_price():
    rows = [
        _row("AAA", 90, 200),
        _row("BBB", 85, 12),
        _row("CCC", 80, 8),
        _row("DDD", 75, None),
    ]
    small = get_small_stock_signals(rows)
    tickers = [item["ticker"] for item in small]
    assert tickers == ["BBB", "CCC"]
    assert "DDD" not in tickers
    assert "AAA" not in tickers


def test_get_small_stock_signals_skips_invalid_price():
    rows = [_row("BAD", 60, "n/a"), _row("GOOD", 70, 10)]
    small = get_small_stock_signals(rows)
    assert len(small) == 1
    assert small[0]["ticker"] == "GOOD"


def test_render_results_html_two_sections_and_no_keyword_list():
    rows = [
        _row("BIG", 95, 120),
        _row("SMALL", 88, 9.5),
    ]
    rows[0].update({"analyst_target_mean": 140.0, "analyst_target_upside_pct": 0.16})
    html = render_results_html(rows)
    assert "General Signals" in html
    assert "Small Stocks Under $15" in html
    assert "Highest-quality Reddit-driven watchlist ideas" in html
    assert "Lower-priced, higher-upside names" in html
    assert "Under $15" in html
    assert "Narrative keywords" not in html
    assert html.count("BIG") >= 1
    assert "SMALL" in html


def test_format_helpers():
    row = {"analyst_target_mean": 50.0, "analyst_target_upside_pct": 0.1, "primary_narrative": "AI demand."}
    assert "$50.00" in format_analyst_target(row)
    assert "+10%" in format_analyst_target(row)
    assert format_narrative(row) == "AI demand."
    assert format_analyst_target({}) == "Street target unavailable"
