"""Subreddit groups and quality weights for weighted scanning."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

SUBREDDIT_GROUPS: dict[str, tuple[str, ...]] = {
    "high_quality": (
        "SecurityAnalysis",
        "ValueInvesting",
        "stocks",
        "investing",
        "StockMarket",
        "options",
        "thetagang",
        "wallstreetbetsOGs",
    ),
    "high_momentum": (
        "wallstreetbets",
        "Daytrading",
        "SwingTrading",
        "Trading",
        "smallstreetbets",
        "Shortsqueeze",
        "squeezeplays",
        "WallstreetbetsELITE",
    ),
    "growth_speculative": (
        "GrowthStocks",
        "FutureInvesting",
        "hypergrowthstocks",
        "SPACs",
        "biotech_stocks",
        "stocksandtrading",
    ),
}

SUBREDDIT_WEIGHTS: dict[str, float] = {
    "SecurityAnalysis": 1.4,
    "ValueInvesting": 1.3,
    "stocks": 1.2,
    "investing": 1.2,
    "StockMarket": 1.1,
    "options": 1.15,
    "thetagang": 1.05,
    "wallstreetbetsOGs": 1.1,
    "wallstreetbets": 1.0,
    "Daytrading": 0.95,
    "SwingTrading": 1.0,
    "Trading": 0.95,
    "smallstreetbets": 0.85,
    "Shortsqueeze": 0.7,
    "squeezeplays": 0.7,
    "WallstreetbetsELITE": 0.6,
    "GrowthStocks": 1.05,
    "FutureInvesting": 1.0,
    "hypergrowthstocks": 0.95,
    "SPACs": 0.75,
    "biotech_stocks": 0.85,
    "stocksandtrading": 0.85,
}

_DEFAULT_WEIGHT = 0.9
_NOISY_THRESHOLD = 0.8
_QUALITY_THRESHOLD = 1.05

_NAME_LOOKUP: dict[str, str] = {}
for _members in SUBREDDIT_GROUPS.values():
    for _name in _members:
        _NAME_LOOKUP[_name.lower()] = _name
for _name in SUBREDDIT_WEIGHTS:
    _NAME_LOOKUP[_name.lower()] = _name


def normalize_subreddit_name(name: str) -> str:
    """Return canonical subreddit casing when known."""

    cleaned = str(name or "").strip()
    if cleaned.startswith("r/"):
        cleaned = cleaned[2:]
    if not cleaned:
        return ""
    return _NAME_LOOKUP.get(cleaned.lower(), cleaned)


def subreddit_weight(name: str) -> float:
    """Return configured weight for a subreddit (default 0.9 for unknown)."""

    canonical = normalize_subreddit_name(name)
    return SUBREDDIT_WEIGHTS.get(canonical, _DEFAULT_WEIGHT)


def subreddit_group(name: str) -> str | None:
    """Return the configured group for a subreddit, if any."""

    canonical = normalize_subreddit_name(name)
    for group, members in SUBREDDIT_GROUPS.items():
        if canonical in members:
            return group
    return None


def all_configured_subreddits() -> tuple[str, ...]:
    """Return every subreddit included in groups/weights."""

    names: list[str] = []
    seen: set[str] = set()
    for group_members in SUBREDDIT_GROUPS.values():
        for name in group_members:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return tuple(names)


def compute_subreddit_metrics(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize weighted subreddit exposure for a ticker."""

    if not sources:
        return {
            "subreddit_groups_detected": [],
            "top_signal_subreddits": [],
            "noisy_subreddit_exposure": 0.0,
            "subreddit_weighted_score": 0.0,
            "high_quality_subreddit_share": 0.0,
        }

    per_sub: dict[str, float] = defaultdict(float)
    groups: set[str] = set()
    weighted_total = 0.0
    noisy_weight = 0.0
    quality_weight = 0.0

    for source in sources:
        sub = normalize_subreddit_name(str(source.get("subreddit") or ""))
        if not sub:
            continue
        weight = subreddit_weight(sub)
        recency = float(source.get("recency_weight") or 1.0)
        contribution = weight * recency
        per_sub[sub] += contribution
        weighted_total += contribution
        group = subreddit_group(sub)
        if group:
            groups.add(group)
        if weight < _NOISY_THRESHOLD:
            noisy_weight += contribution
        if weight >= _QUALITY_THRESHOLD:
            quality_weight += contribution

    total = weighted_total or 1.0
    top_signal = [
        sub for sub, _value in sorted(per_sub.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    avg_weight = weighted_total / len(sources)
    normalized = round(min(1.0, avg_weight / 1.4), 4)

    return {
        "subreddit_groups_detected": sorted(groups),
        "top_signal_subreddits": top_signal,
        "noisy_subreddit_exposure": round(noisy_weight / total, 4),
        "subreddit_weighted_score": normalized,
        "high_quality_subreddit_share": round(quality_weight / total, 4),
    }


def corroboration_factor(metrics: dict[str, Any]) -> float:
    """Boost when quality subs participate; dampen noisy-only signals slightly."""

    quality_share = float(metrics.get("high_quality_subreddit_share") or 0.0)
    noisy_share = float(metrics.get("noisy_subreddit_exposure") or 0.0)
    boost = 0.08 * quality_share
    penalty = 0.06 * max(0.0, noisy_share - 0.65) if quality_share < 0.2 else 0.0
    return round(max(-0.05, min(0.1, boost - penalty)), 4)
