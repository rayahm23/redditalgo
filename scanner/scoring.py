"""Aggregation and ranking logic for ticker mentions."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scanner.market_data import MarketData
from scanner.sentiment import score_post_sentiment
from scanner.ticker_extractor import extract_tickers_from_post

RECENCY_WINDOW_DAYS = 7
RECENCY_WEIGHTS = (1.0, 0.85, 0.70, 0.55, 0.40, 0.25, 0.10)


@dataclass
class TickerAggregate:
    """Intermediate aggregate metrics for one ticker."""

    ticker: str
    mention_count: int = 0
    weighted_mention_count: float = 0.0
    weighted_unique_posts: float = 0.0
    post_ids: set[str] = field(default_factory=set)
    total_upvotes: int = 0
    comment_volume: int = 0
    sentiment_scores: list[float] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unique_posts(self) -> int:
        return len(self.post_ids)

    @property
    def avg_sentiment(self) -> float:
        if not self.sentiment_scores:
            return 0.0
        return round(sum(self.sentiment_scores) / len(self.sentiment_scores), 4)


def _parse_created_utc(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp


def _reference_datetime(reference_time: datetime | str | None = None) -> datetime:
    if reference_time is None:
        return datetime.now(timezone.utc)
    if isinstance(reference_time, datetime):
        return reference_time.astimezone(timezone.utc)
    return datetime.fromisoformat(reference_time.replace("Z", "+00:00")).astimezone(timezone.utc)


def recency_weight(created_utc: Any, reference_time: datetime | str | None = None) -> float:
    """Return a descending mention weight for posts from today through 6 days ago."""

    timestamp = _parse_created_utc(created_utc)
    if timestamp is None:
        return 0.0

    reference = _reference_datetime(reference_time)
    created_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    age_seconds = (reference - created_at).total_seconds()
    if age_seconds < 0:
        age_days = 0
    else:
        age_days = int(age_seconds // 86_400)

    if age_days < 0 or age_days >= RECENCY_WINDOW_DAYS:
        return 0.0
    return RECENCY_WEIGHTS[age_days]


def aggregate_posts(
    posts: list[dict[str, Any]],
    excluded: set[str] | None = None,
    reference_time: datetime | str | None = None,
) -> dict[str, TickerAggregate]:
    """Aggregate Reddit posts from the last 7 days into per-ticker metrics."""

    aggregates: dict[str, TickerAggregate] = {}
    reference = _reference_datetime(reference_time)

    for index, post in enumerate(posts):
        weight = recency_weight(post.get("created_utc"), reference)
        if weight <= 0:
            continue

        comments = post.get("top_comments") or []
        mentions = extract_tickers_from_post(
            post.get("title"), post.get("selftext"), comments, excluded=excluded
        )
        if not mentions:
            continue

        mention_counts = Counter(mentions)
        post_id = str(post.get("id") or post.get("permalink") or index)
        sentiment = score_post_sentiment(post.get("title"), post.get("selftext"), comments)
        score = int(post.get("score") or 0)
        num_comments = int(post.get("num_comments") or 0)

        for ticker, count in mention_counts.items():
            aggregate = aggregates.setdefault(ticker, TickerAggregate(ticker=ticker))
            aggregate.mention_count += count
            aggregate.weighted_mention_count += count * weight
            aggregate.weighted_unique_posts += weight
            aggregate.post_ids.add(post_id)
            aggregate.total_upvotes += score
            aggregate.comment_volume += num_comments
            aggregate.sentiment_scores.append(sentiment)
            aggregate.sources.append(
                {
                    "subreddit": post.get("subreddit"),
                    "title": post.get("title"),
                    "permalink": post.get("permalink"),
                    "score": score,
                    "created_utc": post.get("created_utc"),
                    "recency_weight": round(weight, 2),
                }
            )
    return aggregates


def risk_details(market_data: MarketData) -> dict[str, Any]:
    """Return risk flag, reasons, and thresholds used for classification."""

    thresholds = {
        "penny_stock_price_lt": 5,
        "low_avg_volume_lt": 500_000,
        "small_market_cap_lt": 300_000_000,
        "low_risk_avg_volume_gte": 2_000_000,
        "low_risk_market_cap_gte": 10_000_000_000,
    }
    reasons: list[str] = []

    if not market_data.valid:
        return {
            "risk_flag": "high",
            "risk_reasons": ["No valid market data was available for this ticker."],
            "risk_thresholds": thresholds,
        }

    latest_price = market_data.latest_price
    avg_volume = market_data.avg_volume
    market_cap = market_data.market_cap

    if latest_price is not None and latest_price < thresholds["penny_stock_price_lt"]:
        reasons.append("Penny stock: latest price is below $5.")
    if avg_volume is not None and avg_volume < thresholds["low_avg_volume_lt"]:
        reasons.append("Low liquidity: average volume is below 500,000 shares.")
    if market_cap is not None and market_cap < thresholds["small_market_cap_lt"]:
        reasons.append("Small market cap: market cap is below $300M.")

    if reasons:
        return {"risk_flag": "high", "risk_reasons": reasons, "risk_thresholds": thresholds}

    if (
        latest_price is not None
        and latest_price >= thresholds["penny_stock_price_lt"]
        and avg_volume is not None
        and avg_volume >= thresholds["low_risk_avg_volume_gte"]
        and market_cap is not None
        and market_cap >= thresholds["low_risk_market_cap_gte"]
    ):
        return {
            "risk_flag": "low",
            "risk_reasons": [
                "Liquid large-cap profile: price is at least $5, average volume is at least 2M, and market cap is at least $10B."
            ],
            "risk_thresholds": thresholds,
        }

    return {
        "risk_flag": "medium",
        "risk_reasons": [
            "Valid market data is available, but the ticker does not meet all low-risk liquidity and market-cap thresholds."
        ],
        "risk_thresholds": thresholds,
    }


def determine_risk_flag(market_data: MarketData) -> str:
    """Classify ticker risk from simple market-data heuristics."""

    return str(risk_details(market_data)["risk_flag"])


def score_breakdown(aggregate: TickerAggregate, market_data: MarketData) -> dict[str, Any]:
    """Calculate component scores used to produce final_score."""

    attention_score = math.log1p(aggregate.weighted_mention_count) * 14 + aggregate.weighted_unique_posts * 5
    engagement_score = math.log1p(max(aggregate.total_upvotes, 0)) * 6 + math.log1p(
        max(aggregate.comment_volume, 0)
    ) * 4
    sentiment_score = ((aggregate.avg_sentiment + 1) / 2) * 22
    validity_bonus = 8 if market_data.valid else 0
    risk_penalty = {"high": 10, "medium": 4, "low": 0}[determine_risk_flag(market_data)]
    raw_score = attention_score + engagement_score + sentiment_score + validity_bonus
    capped_score = min(100.0, raw_score)
    final_score = max(0.0, capped_score - risk_penalty)

    return {
        "attention_score": round(attention_score, 2),
        "engagement_score": round(engagement_score, 2),
        "sentiment_score": round(sentiment_score, 2),
        "market_validity_bonus": validity_bonus,
        "risk_penalty": risk_penalty,
        "raw_score_before_cap": round(raw_score, 2),
        "capped_score_before_risk": round(capped_score, 2),
        "final_score": round(final_score, 2),
        "recency_window_days": RECENCY_WINDOW_DAYS,
        "recency_weights": list(RECENCY_WEIGHTS),
        "formula": "min(100, attention + engagement + sentiment + market_validity_bonus) - risk_penalty",
    }


def calculate_final_score(aggregate: TickerAggregate, market_data: MarketData) -> float:
    """Calculate an explainable 0-100 score from attention, sentiment, and risk."""

    return float(score_breakdown(aggregate, market_data)["final_score"])


def build_summary(aggregate: TickerAggregate, risk_flag: str) -> str:
    """Produce a compact human-readable explanation for a ranked ticker."""

    sentiment = aggregate.avg_sentiment
    if sentiment >= 0.25:
        sentiment_label = "positive sentiment"
    elif sentiment <= -0.25:
        sentiment_label = "negative sentiment"
    else:
        sentiment_label = "mixed sentiment"

    attention_label = (
        "high recent Reddit attention"
        if aggregate.weighted_mention_count >= 8 or aggregate.unique_posts >= 5
        else "emerging recent Reddit attention"
    )
    risk_note = "high-risk market profile" if risk_flag == "high" else f"{risk_flag}-risk market profile"
    return f"{attention_label.capitalize()} with {sentiment_label} and a {risk_note}."


def rank_tickers(
    aggregates: dict[str, TickerAggregate],
    market_data_by_ticker: dict[str, MarketData],
    limit: int = 15,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Rank valid tickers and return JSON-serializable result rows."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for ticker, aggregate in aggregates.items():
        market_data = market_data_by_ticker.get(ticker, MarketData(valid=False))
        if not market_data.valid:
            continue

        details = risk_details(market_data)
        risk_flag = str(details["risk_flag"])
        breakdown = score_breakdown(aggregate, market_data)
        top_sources = sorted(
            aggregate.sources,
            key=lambda source: (float(source.get("recency_weight") or 0), int(source.get("score") or 0)),
            reverse=True,
        )[:3]
        top_sources = [
            {
                "subreddit": source.get("subreddit"),
                "title": source.get("title"),
                "permalink": source.get("permalink"),
                "created_utc": source.get("created_utc"),
                "recency_weight": source.get("recency_weight"),
            }
            for source in top_sources
        ]

        rows.append(
            {
                "ticker": ticker,
                "final_score": breakdown["final_score"],
                "mention_count": aggregate.mention_count,
                "weighted_mention_count": round(aggregate.weighted_mention_count, 2),
                "unique_posts": aggregate.unique_posts,
                "weighted_unique_posts": round(aggregate.weighted_unique_posts, 2),
                "avg_sentiment": aggregate.avg_sentiment,
                "total_upvotes": aggregate.total_upvotes,
                "comment_volume": aggregate.comment_volume,
                "latest_price": market_data.latest_price,
                "market_cap": market_data.market_cap,
                "avg_volume": market_data.avg_volume,
                "risk_flag": risk_flag,
                "risk_reasons": details["risk_reasons"],
                "risk_thresholds": details["risk_thresholds"],
                "score_breakdown": breakdown,
                "summary": build_summary(aggregate, risk_flag),
                "top_sources": top_sources,
                "generated_at": generated_at,
            }
        )

    rows.sort(key=lambda row: row["final_score"], reverse=True)
    for rank, row in enumerate(rows[:limit], start=1):
        row["rank"] = rank

    return rows[:limit]
