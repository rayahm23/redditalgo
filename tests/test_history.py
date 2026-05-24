import json
from datetime import date
from pathlib import Path

from scanner.history import (
    attention_acceleration_score,
    build_historical_trends,
    build_sparkline_payload,
    calculate_historical_baselines,
    load_history_snapshots,
    smooth_series,
    smoothed_attention_acceleration,
)


def test_smooth_series_reduces_noise():
    raw = [1.0, 10.0, 2.0, 9.0, 3.0]
    smoothed = smooth_series(raw, alpha=0.35)
    assert len(smoothed) == len(raw)
    assert smoothed[-1] < raw[-2]


def test_smoothed_attention_acceleration_uses_trailing_baseline():
    mentions = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 8.0]
    value = smoothed_attention_acceleration(mentions)
    assert value > 1.0
    assert attention_acceleration_score(value) <= 1.0


def test_build_historical_trends_and_sparklines(tmp_path: Path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    prior = [
        {
            "ticker": "TSLA",
            "mention_count": 4,
            "avg_sentiment": 0.2,
            "final_score": 55.0,
            "analyst_target_score": 0.33,
        }
    ]
    (history_dir / "2026-05-22.json").write_text(json.dumps(prior), encoding="utf-8")
    (history_dir / "2026-05-23.json").write_text(json.dumps(prior), encoding="utf-8")

    snapshots = load_history_snapshots(history_dir, "2026-05-24", days=7)
    trends = build_historical_trends(
        "TSLA",
        snapshots,
        current_mentions=9,
        current_sentiment=0.5,
        current_score=70.0,
        current_analyst_target=0.67,
    )
    sparklines = build_sparkline_payload(trends)

    assert len(trends["mentions_7d"]) == 7
    assert trends["mentions_7d"][-1] == 9
    assert trends["mentions_7d"][0] == 0
    assert trends["mentions_7d"][-3] == 4
    assert sparklines["mentions"] == trends["mentions_7d"]
    assert sparklines["length"] == 7


def test_calculate_historical_baselines_averages_mentions():
    rows = [
        {"ticker": "TSLA", "mention_count": 4},
        {"ticker": "TSLA", "mention_count": 6},
        {"ticker": "NVDA", "mention_count": 2},
    ]
    baselines = calculate_historical_baselines(rows, days=2)
    assert baselines["TSLA"]["seven_day_avg_mentions"] == 5.0
    assert baselines["NVDA"]["seven_day_avg_mentions"] == 1.0
