from datetime import date

from scanner.backtest import _pending_reason, build_backtest_summary


def test_pending_reason_when_insufficient_days():
    assert _pending_reason(2, 7) == "Not enough forward data yet"
    assert _pending_reason(10, 7) is None


def test_backtest_summary_more_history_message():
    summary = build_backtest_summary([])
    assert summary["total_signals"] == 0
    assert "history" in (summary.get("message") or "").lower()

    summary_small = build_backtest_summary(
        [
            {
                "pending": False,
                "return_7d": 0.05,
                "recommendation_type": "Watchlist",
                "confidence_label": "MEDIUM",
            }
        ]
    )
    assert summary_small["total_completed_signals"] == 1
