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


@dataclass
class TickerAggregate:
    """Intermediate aggregate metrics for one ticker."""

    ticker: str
    mention_count: int = 0
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


def aggregate_posts(posts: list[dict[str, Any]], excluded: set[str] | None = None) -> dict[str, TickerAggregate]:
    """Aggregate Reddit posts into per-ticker metrics."""

    aggregates: dict[str, TickerAggregate] = {}
    for index, post in enumerate(posts):
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
                }
            )
    return aggregates


def determine_risk_flag(market_data: MarketData) -> str:
    """Classify ticker risk from simple market-data heuristics."""

    if not market_data.valid:
        return "high"

    latest_price = market_data.latest_price
    avg_volume = market_data.avg_volume
    market_cap = market_data.market_cap

    if (
        (latest_price is not None and latest_price < 5)
        or (avg_volume is not None and avg_volume < 500_000)
        or (market_cap is not None and market_cap < 300_000_000)
    ):
        return "high"

    if (
        latest_price is not None
        and latest_price >= 5
        and avg_volume is not None
        and avg_volume >= 2_000_000
        and market_cap is not None
        and market_cap >= 10_000_000_000
    ):
        return "low"

    return "medium"


def calculate_final_score(aggregate: TickerAggregate, market_data: MarketData) -> float:
    """Calculate an explainable 0-100 score from attention, sentiment, and risk."""

    attention_score = math.log1p(aggregate.mention_count) * 12 + aggregate.unique_posts * 4
    engagement_score = math.log1p(max(aggregate.total_upvotes, 0)) * 6 + math.log1p(
        max(aggregate.comment_volume, 0)
    ) * 4
    sentiment_score = ((aggregate.avg_sentiment + 1) / 2) * 22
    validity_bonus = 8 if market_data.valid else 0
    risk_penalty = {"high": 10, "medium": 4, "low": 0}[determine_risk_flag(market_data)]

    score = attention_score + engagement_score + sentiment_score + validity_bonus - risk_penalty
    return round(max(0.0, min(100.0, score)), 2)


def build_summary(aggregate: TickerAggregate, risk_flag: str) -> str:
    """Produce a compact human-readable explanation for a ranked ticker."""

    sentiment = aggregate.avg_sentiment
    if sentiment >= 0.25:
        sentiment_label = "positive sentiment"
    elif sentiment <= -0.25:
        sentiment_label = "negative sentiment"
    else:
        sentiment_label = "mixed sentiment"

    attention_label = "high Reddit attention" if aggregate.unique_posts >= 5 or aggregate.mention_count >= 10 else "emerging Reddit attention"
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

        risk_flag = determine_risk_flag(market_data)
        top_sources = sorted(
            aggregate.sources,
            key=lambda source: int(source.get("score") or 0),
            reverse=True,
        )[:3]
        top_sources = [
            {
                "subreddit": source.get("subreddit"),
                "title": source.get("title"),
                "permalink": source.get("permalink"),
            }
            for source in top_sources
        ]

        rows.append(
            {
                "ticker": ticker,
                "final_score": calculate_final_score(aggregate, market_data),
                "mention_count": aggregate.mention_count,
                "unique_posts": aggregate.unique_posts,
                "avg_sentiment": aggregate.avg_sentiment,
                "total_upvotes": aggregate.total_upvotes,
                "comment_volume": aggregate.comment_volume,
                "latest_price": market_data.latest_price,
                "market_cap": market_data.market_cap,
                "avg_volume": market_data.avg_volume,
                "risk_flag": risk_flag,
                "summary": build_summary(aggregate, risk_flag),
                "top_sources": top_sources,
                "generated_at": generated_at,
            }
        )

    rows.sort(key=lambda row: row["final_score"], reverse=True)
    for rank, row in enumerate(rows[:limit], start=1):
        row["rank"] = rank

    return rows[:limit]
