"""Historical scanner result helpers."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


TREND_WINDOW_DAYS = 7
DEFAULT_SMOOTHING_ALPHA = 0.4


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value[:10]).date()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ticker_row_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("ticker") or "").upper(): row for row in rows if row.get("ticker")}


def load_recent_history(history_dir: Path, run_date: str | date, days: int = 7) -> list[dict[str, Any]]:
    """Load result rows from the prior N daily history JSON files."""

    current = _parse_date(run_date)
    rows: list[dict[str, Any]] = []
    for offset in range(1, days + 1):
        path = history_dir / f"{current - timedelta(days=offset)}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            rows.extend(row for row in payload if isinstance(row, dict))
    return rows


def load_history_snapshots(
    history_dir: Path,
    run_date: str | date,
    days: int = TREND_WINDOW_DAYS,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Load daily snapshots oldest-first for the trailing window ending on run_date."""

    current = _parse_date(run_date)
    snapshots: list[tuple[str, list[dict[str, Any]]]] = []
    for offset in range(days - 1, -1, -1):
        day = current - timedelta(days=offset)
        day_key = day.isoformat()
        path = history_dir / f"{day_key}.json"
        rows: list[dict[str, Any]] = []
        if path.exists() and offset > 0:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = []
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
        snapshots.append((day_key, rows))
    return snapshots


def calculate_historical_baselines(history_rows: list[dict[str, Any]], days: int = 7) -> dict[str, dict[str, float]]:
    """Calculate average mention baselines from prior result rows."""

    totals: dict[str, float] = {}
    for row in history_rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        totals[ticker] = totals.get(ticker, 0.0) + _safe_float(row.get("mention_count"))

    return {
        ticker: {"seven_day_avg_mentions": round(total / days, 4)}
        for ticker, total in totals.items()
    }


def smooth_series(values: list[float], alpha: float = DEFAULT_SMOOTHING_ALPHA) -> list[float]:
    """Apply exponential smoothing to reduce day-to-day acceleration noise."""

    if not values:
        return []
    smoothed = [round(values[0], 4)]
    for value in values[1:]:
        next_value = alpha * value + (1 - alpha) * smoothed[-1]
        smoothed.append(round(next_value, 4))
    return smoothed


def attention_acceleration_score(attention_acceleration: float) -> float:
    """Normalize mention acceleration to a 0-1 score."""

    if attention_acceleration <= 0:
        return 0.0
    # 1x baseline = 0.25, 2x = 0.5, 4x or higher = 1.0.
    return round(max(0.0, min(1.0, attention_acceleration / 4)), 4)


def smoothed_attention_acceleration(mentions_7d: list[float], alpha: float = DEFAULT_SMOOTHING_ALPHA) -> float:
    """Compute acceleration from smoothed recent mentions vs trailing baseline."""

    if not mentions_7d:
        return 0.0

    smoothed = smooth_series(mentions_7d, alpha=alpha)
    recent = smoothed[-1]
    if len(smoothed) > 1:
        baseline = sum(smoothed[:-1]) / (len(smoothed) - 1)
    else:
        baseline = smoothed[0]
    return round(recent / max(baseline, 1.0), 4)


def _metric_from_row(row: dict[str, Any] | None, key: str, fallback: float = 0.0) -> float:
    if not row:
        return fallback
    if key == "analyst_target_upside":
        return round(_safe_float(row.get("analyst_target_score")), 4)
    if key == "score":
        return round(_safe_float(row.get("final_score")), 2)
    if key == "sentiment":
        return round(_safe_float(row.get("avg_sentiment")), 4)
    if key == "mentions":
        return round(_safe_float(row.get("mention_count")), 2)
    return fallback


def build_historical_trends(
    ticker: str,
    snapshots: list[tuple[str, list[dict[str, Any]]]],
    *,
    current_mentions: float,
    current_sentiment: float,
    current_score: float,
    current_analyst_target: float,
) -> dict[str, list[float]]:
    """Build 7-day trend arrays (oldest to newest) for a ticker."""

    symbol = ticker.upper()
    mentions_7d: list[float] = []
    sentiment_7d: list[float] = []
    score_7d: list[float] = []
    analyst_target_upside_7d: list[float] = []

    for index, (_day, rows) in enumerate(snapshots):
        index_by_ticker = _ticker_row_index(rows)
        row = index_by_ticker.get(symbol)
        is_today = index == len(snapshots) - 1
        if is_today:
            mentions_7d.append(round(current_mentions, 2))
            sentiment_7d.append(round(current_sentiment, 4))
            score_7d.append(round(current_score, 2))
            analyst_target_upside_7d.append(round(current_analyst_target, 4))
        else:
            mentions_7d.append(_metric_from_row(row, "mentions"))
            sentiment_7d.append(_metric_from_row(row, "sentiment"))
            score_7d.append(_metric_from_row(row, "score"))
            analyst_target_upside_7d.append(_metric_from_row(row, "analyst_target_upside"))

    return {
        "mentions_7d": mentions_7d,
        "sentiment_7d": sentiment_7d,
        "score_7d": score_7d,
        "analyst_target_upside_7d": analyst_target_upside_7d,
    }


def build_sparkline_payload(historical_trends: dict[str, list[float]]) -> dict[str, Any]:
    """Return sparkline-ready arrays and date labels for frontend charts."""

    return {
        "mentions": historical_trends.get("mentions_7d", []),
        "sentiment": historical_trends.get("sentiment_7d", []),
        "score": historical_trends.get("score_7d", []),
        "analyst_target_upside": historical_trends.get("analyst_target_upside_7d", []),
        "length": TREND_WINDOW_DAYS,
    }


def catalyst_type_label(dominant_post_type: str, catalyst_confidence: float) -> str:
    """Return a compact catalyst label for UI chips."""

    label = dominant_post_type or "Other"
    if catalyst_confidence >= 0.7 and label not in {"Meme", "Question", "YOLO"}:
        return label
    if catalyst_confidence >= 0.45:
        return label
    return "Mixed"
