"""Historical scanner result helpers."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value[:10]).date()


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


def calculate_historical_baselines(history_rows: list[dict[str, Any]], days: int = 7) -> dict[str, dict[str, float]]:
    """Calculate average mention baselines from prior result rows."""

    totals: dict[str, float] = {}
    for row in history_rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        try:
            mentions = float(row.get("mention_count") or 0)
        except (TypeError, ValueError):
            mentions = 0.0
        totals[ticker] = totals.get(ticker, 0.0) + mentions

    return {
        ticker: {"seven_day_avg_mentions": round(total / days, 4)}
        for ticker, total in totals.items()
    }


def attention_acceleration_score(attention_acceleration: float) -> float:
    """Normalize smoothed mention acceleration to a 0-1 score using log scaling."""

    if attention_acceleration <= 0:
        return 0.0
    # Log scaling keeps large spikes explainable without letting extreme ratios dominate.
    return round(max(0.0, min(1.0, math.log1p(attention_acceleration) / math.log1p(4))), 4)
