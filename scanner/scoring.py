"""Aggregation and ranking logic for ticker mentions."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scanner.conviction import conviction_scores
from scanner.history import attention_acceleration_score
from scanner.market_data import MarketData
from scanner.post_classifier import dominant_post_type as choose_dominant_post_type
from scanner.post_classifier import classify_post, post_type_weight
from scanner.sentiment import score_post_sentiment
from scanner.ticker_extractor import extract_tickers_from_post

RECENCY_WINDOW_DAYS = 7
RECENCY_WEIGHTS = (1.0, 0.85, 0.70, 0.55, 0.40, 0.25, 0.10)
ROCKET_TERMS = ("🚀", "🌕", "moon", "mooning", "lambo", "tendies")
HIGH_QUALITY_DISCUSSION_TERMS = (
    "guidance",
    "valuation",
    "dcf",
    "free cash flow",
    "fcf",
    "margin expansion",
    "capex",
    "eps",
    "institutional",
    "ebitda",
)
LOW_QUALITY_HYPE_TERMS = (
    "moon",
    "lambo",
    "yolo",
    "diamond hands",
    "ape",
    "rocket",
    "trust me bro",
    "🚀",
)
BULLISH_ATTENTION_PHRASES = (
    "buying calls",
    "calls",
    "call options",
    "accumulating",
    "accumulation",
    "adding",
    "loading",
    "loaded",
    "long",
    "bullish",
    "breakout",
    "squeeze",
    "undervalued",
    "price target",
    "raised guidance",
    "beat earnings",
)
BEARISH_ATTENTION_PHRASES = (
    "puts",
    "put options",
    "shorting",
    "shorted",
    "selloff",
    "sell-off",
    "selling",
    "dumping",
    "bearish",
    "overvalued",
    "downside",
    "dilution",
    "bankruptcy",
    "lowered guidance",
    "missed earnings",
    "rug pull",
)


@dataclass
class TickerAggregate:
    """Intermediate aggregate metrics for one ticker."""

    ticker: str
    mention_count: int = 0
    weighted_mention_count: float = 0.0
    weighted_unique_posts: float = 0.0
    post_ids: set[str] = field(default_factory=set)
    subreddits: set[str] = field(default_factory=set)
    total_upvotes: int = 0
    comment_volume: int = 0
    sentiment_scores: list[float] = field(default_factory=list)
    post_types: list[str] = field(default_factory=list)
    post_type_weights: list[float] = field(default_factory=list)
    bullish_scores: list[float] = field(default_factory=list)
    bearish_scores: list[float] = field(default_factory=list)
    bullish_attention_scores: list[float] = field(default_factory=list)
    bearish_attention_scores: list[float] = field(default_factory=list)
    hype_count: int = 0
    max_repeated_mentions: int = 0
    low_quality_mentions: int = 0
    unique_users: set[str] = field(default_factory=set)
    upvote_ratios: list[float] = field(default_factory=list)
    max_post_upvotes: int = 0
    max_post_comments: int = 0
    high_quality_terms: set[str] = field(default_factory=set)
    low_quality_terms: set[str] = field(default_factory=set)
    sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unique_posts(self) -> int:
        return len(self.post_ids)

    @property
    def unique_subreddits(self) -> int:
        return len(self.subreddits)

    @property
    def unique_user_count(self) -> int:
        return len(self.unique_users)

    @property
    def comments_per_post(self) -> float:
        if self.unique_posts <= 0:
            return 0.0
        return round(self.comment_volume / self.unique_posts, 4)

    @property
    def avg_upvote_ratio(self) -> float:
        if not self.upvote_ratios:
            return 0.0
        return round(sum(self.upvote_ratios) / len(self.upvote_ratios), 4)

    @property
    def avg_sentiment(self) -> float:
        if not self.sentiment_scores:
            return 0.0
        return round(sum(self.sentiment_scores) / len(self.sentiment_scores), 4)

    @property
    def post_type_weight_avg(self) -> float:
        if not self.post_type_weights:
            return 1.0
        return round(sum(self.post_type_weights) / len(self.post_type_weights), 4)

    @property
    def dominant_post_type(self) -> str:
        return choose_dominant_post_type(self.post_types)

    @property
    def bullish_conviction_score(self) -> float:
        return round(sum(self.bullish_scores) / len(self.bullish_scores), 4) if self.bullish_scores else 0.0

    @property
    def bearish_conviction_score(self) -> float:
        return round(sum(self.bearish_scores) / len(self.bearish_scores), 4) if self.bearish_scores else 0.0

    @property
    def net_conviction_score(self) -> float:
        bullish = self.bullish_conviction_score
        bearish = self.bearish_conviction_score
        return round(max(0.0, min(1.0, 0.5 + (bullish - bearish) / 2)), 4)

    @property
    def bullish_attention_score(self) -> float:
        if not self.bullish_attention_scores:
            return 0.0
        return round(sum(self.bullish_attention_scores) / len(self.bullish_attention_scores), 4)

    @property
    def bearish_attention_score(self) -> float:
        if not self.bearish_attention_scores:
            return 0.0
        return round(sum(self.bearish_attention_scores) / len(self.bearish_attention_scores), 4)

    @property
    def net_positioning_score(self) -> float:
        bullish = self.bullish_attention_score
        bearish = self.bearish_attention_score
        return round(max(0.0, min(1.0, 0.5 + (bullish - bearish) / 2)), 4)

    @property
    def high_quality_terms_found(self) -> list[str]:
        return _ordered_terms(self.high_quality_terms, HIGH_QUALITY_DISCUSSION_TERMS)

    @property
    def low_quality_terms_found(self) -> list[str]:
        return _ordered_terms(self.low_quality_terms, LOW_QUALITY_HYPE_TERMS)


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
    age_days = 0 if age_seconds < 0 else int(age_seconds // 86_400)

    if age_days < 0 or age_days >= RECENCY_WINDOW_DAYS:
        return 0.0
    return RECENCY_WEIGHTS[age_days]


def _hype_count(*parts: Any) -> int:
    text = " ".join(str(part or "") for part in parts).lower()
    return sum(text.count(term.lower()) for term in ROCKET_TERMS)


def _text_blob(*parts: Any) -> str:
    return f" {' '.join(str(part or '') for part in parts).lower()} "


def _term_in_text(text: str, term: str) -> bool:
    lowered = term.lower()
    if not any(character.isalnum() for character in lowered):
        return lowered in text
    return re.search(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])", text) is not None


def _terms_found(text: str, terms: tuple[str, ...]) -> set[str]:
    return {term for term in terms if _term_in_text(text, term)}


def _ordered_terms(found: set[str], vocabulary: tuple[str, ...]) -> list[str]:
    return [term for term in vocabulary if term in found]


def _attention_phrase_score(text: str, phrases: tuple[str, ...]) -> float:
    matches = _terms_found(text, phrases)
    return round(min(1.0, len(matches) / 5), 4)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def attention_acceleration(today_mentions: int | float, seven_day_avg_mentions: int | float) -> float:
    """Return smoothed current attention relative to the historical baseline."""

    return (max(float(today_mentions), 0.0) + 3) / (max(float(seven_day_avg_mentions), 0.0) + 3)


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
        subreddit = str(post.get("subreddit") or "")
        post_type = classify_post(post.get("title"), post.get("selftext"), comments)
        type_weight = post_type_weight(post_type)
        conviction = conviction_scores(post.get("title"), post.get("selftext"), comments)
        hype = _hype_count(post.get("title"), post.get("selftext"), " ".join(comments))
        text = _text_blob(post.get("title"), post.get("selftext"), " ".join(comments))
        high_quality_terms = _terms_found(text, HIGH_QUALITY_DISCUSSION_TERMS)
        low_quality_terms = _terms_found(text, LOW_QUALITY_HYPE_TERMS)
        bullish_attention = _attention_phrase_score(text, BULLISH_ATTENTION_PHRASES)
        bearish_attention = _attention_phrase_score(text, BEARISH_ATTENTION_PHRASES)
        upvote_ratio = _safe_float(post.get("upvote_ratio"))
        author = str(post.get("author") or post.get("author_name") or post.get("username") or "").strip()
        is_low_quality_context = post_type in {"Meme", "Question", "YOLO"} and score < 25 and num_comments < 15

        for ticker, count in mention_counts.items():
            aggregate = aggregates.setdefault(ticker, TickerAggregate(ticker=ticker))
            aggregate.mention_count += count
            aggregate.weighted_mention_count += count * weight
            aggregate.weighted_unique_posts += weight
            aggregate.post_ids.add(post_id)
            if subreddit:
                aggregate.subreddits.add(subreddit)
            aggregate.total_upvotes += score
            aggregate.comment_volume += num_comments
            aggregate.sentiment_scores.append(sentiment)
            aggregate.post_types.append(post_type)
            aggregate.post_type_weights.append(type_weight)
            aggregate.bullish_scores.append(conviction["bullish_conviction_score"])
            aggregate.bearish_scores.append(conviction["bearish_conviction_score"])
            aggregate.bullish_attention_scores.append(bullish_attention)
            aggregate.bearish_attention_scores.append(bearish_attention)
            aggregate.hype_count += hype
            aggregate.max_repeated_mentions = max(aggregate.max_repeated_mentions, count)
            aggregate.max_post_upvotes = max(aggregate.max_post_upvotes, score)
            aggregate.max_post_comments = max(aggregate.max_post_comments, num_comments)
            if author and author.lower() not in {"[deleted]", "deleted", "automoderator"}:
                aggregate.unique_users.add(author)
            if upvote_ratio is not None and 0 < upvote_ratio <= 1:
                aggregate.upvote_ratios.append(upvote_ratio)
            aggregate.high_quality_terms.update(high_quality_terms)
            aggregate.low_quality_terms.update(low_quality_terms)
            if count == 1 and is_low_quality_context:
                aggregate.low_quality_mentions += 1
            aggregate.sources.append(
                {
                    "subreddit": subreddit,
                    "title": post.get("title"),
                    "permalink": post.get("permalink"),
                    "score": score,
                    "created_utc": post.get("created_utc"),
                    "recency_weight": round(weight, 2),
                    "post_type": post_type,
                    "author": author or None,
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


def engagement_quality_score(aggregate: TickerAggregate) -> float:
    """Score engagement quality from 0 to 1, favoring broad participation over one viral post."""

    effective_users = aggregate.unique_user_count or aggregate.unique_posts
    unique_user_score = min(1.0, math.log1p(max(effective_users, 0)) / math.log1p(25))
    comments_per_post_score = min(1.0, math.log1p(max(aggregate.comments_per_post, 0.0)) / math.log1p(150))
    upvote_ratio_score = aggregate.avg_upvote_ratio if aggregate.upvote_ratios else 0.5
    sustained_discussion_score = 0.0
    if aggregate.unique_posts > 1:
        sustained_discussion_score = min(1.0, math.log1p(aggregate.unique_posts - 1) / math.log1p(9))

    total_upvotes = max(aggregate.total_upvotes, 0)
    total_comments = max(aggregate.comment_volume, 0)
    upvote_dominance = aggregate.max_post_upvotes / total_upvotes if total_upvotes else 0.0
    comment_dominance = aggregate.max_post_comments / total_comments if total_comments else 0.0
    dominance = max(upvote_dominance, comment_dominance)
    concentration_factor = 1.0
    if aggregate.unique_posts <= 1:
        concentration_factor = 0.75
    elif dominance > 0.55:
        concentration_factor = max(0.55, 1 - (dominance - 0.55))

    score = (
        0.30 * unique_user_score
        + 0.25 * comments_per_post_score
        + 0.25 * upvote_ratio_score
        + 0.20 * sustained_discussion_score
    ) * concentration_factor
    return round(max(0.0, min(1.0, score)), 4)


def discussion_quality_score(aggregate: TickerAggregate) -> float:
    """Score whether discussion sounds research-driven instead of hype-driven."""

    high_quality_score = min(1.0, len(aggregate.high_quality_terms) / 4)
    low_quality_penalty = min(1.0, len(aggregate.low_quality_terms) / 4)
    post_type_quality = min(1.0, aggregate.post_type_weight_avg / 1.5)
    sustained_score = min(1.0, math.log1p(max(aggregate.unique_posts, 0)) / math.log1p(5))
    subreddit_score = subreddit_spread_score(aggregate.unique_subreddits)

    score = (
        0.45 * high_quality_score
        + 0.20 * post_type_quality
        + 0.20 * sustained_score
        + 0.15 * subreddit_score
        - 0.35 * low_quality_penalty
    )
    return round(max(0.0, min(1.0, score)), 4)


def normalized_sentiment_score(avg_sentiment: float) -> float:
    return round(max(0.0, min(1.0, (avg_sentiment + 1) / 2)), 4)


def market_confirmation_score(market_data: MarketData) -> float:
    """Score market confirmation from 0 to 1."""

    if not market_data.valid:
        return 0.0

    score = 0.15
    if market_data.one_day_return is not None:
        score += 0.15 if market_data.one_day_return > 0 else -0.08
    if market_data.five_day_return is not None:
        score += 0.20 if market_data.five_day_return > 0 else -0.10
    if market_data.relative_volume is not None:
        if market_data.relative_volume >= 1.5:
            score += 0.25
        elif market_data.relative_volume >= 1.0:
            score += 0.10
    if market_data.above_20_day_high:
        score += 0.25
    if market_data.avg_volume is not None and market_data.avg_volume < 500_000:
        score -= 0.20

    return round(max(0.0, min(1.0, score)), 4)


def subreddit_spread_score(unique_subreddits: int) -> float:
    if unique_subreddits <= 0:
        return 0.0
    return round(min(1.0, unique_subreddits * 0.25), 4)


def pump_risk_details(aggregate: TickerAggregate, market_data: MarketData, market_score: float) -> dict[str, Any]:
    """Calculate pump/noise risk and explanation."""

    components: list[float] = []
    reasons: list[str] = []

    hype_component = min(1.0, aggregate.hype_count / 8)
    if hype_component >= 0.25:
        reasons.append("Heavy rocket/moon/hype language detected.")
    components.append(hype_component)

    repeated_component = min(1.0, max(0, aggregate.max_repeated_mentions - 3) / 7)
    if repeated_component > 0:
        reasons.append("Ticker is repeated many times within the same post/comment context.")
    components.append(repeated_component)

    if market_data.latest_price is not None and market_data.latest_price < 5:
        components.append(0.8)
        reasons.append("Penny stock price increases pump risk.")
    if market_data.avg_volume is not None and market_data.avg_volume < 500_000:
        components.append(0.7)
        reasons.append("Low average volume increases manipulation/noise risk.")
    if market_data.market_cap is not None and market_data.market_cap < 300_000_000:
        components.append(0.7)
        reasons.append("Very small market cap increases pump risk.")

    meme_yolo_share = 0.0
    if aggregate.post_types:
        meme_yolo_share = sum(1 for item in aggregate.post_types if item in {"Meme", "YOLO"}) / len(aggregate.post_types)
    components.append(meme_yolo_share)
    if meme_yolo_share >= 0.5:
        reasons.append("Most discussion is meme/YOLO driven.")

    if aggregate.avg_sentiment >= 0.45 and market_score < 0.35:
        components.append(0.6)
        reasons.append("Sentiment is high but market confirmation is weak.")

    if aggregate.low_quality_mentions and aggregate.mention_count <= 2:
        components.append(0.4)
        reasons.append("Ticker appears only in low-quality one-off contexts.")

    score = sum(components) / len(components) if components else 0.0
    return {
        "pump_risk_score": round(max(0.0, min(1.0, score)), 4),
        "risk_explanation": " ".join(reasons) if reasons else "No major pump/noise signals detected.",
    }


def score_breakdown(
    aggregate: TickerAggregate,
    market_data: MarketData,
    baseline: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Calculate component scores used to produce final_score."""

    baseline = baseline or {}
    seven_day_avg_mentions = float(baseline.get("seven_day_avg_mentions", 0.0) or 0.0)
    acceleration = attention_acceleration(aggregate.mention_count, seven_day_avg_mentions)
    log_acceleration = math.log1p(acceleration)
    acceleration_score = attention_acceleration_score(acceleration)
    engagement_score = engagement_quality_score(aggregate)
    sentiment_score = normalized_sentiment_score(aggregate.avg_sentiment)
    net_conviction = aggregate.net_conviction_score
    market_score = market_confirmation_score(market_data)
    discussion_score = discussion_quality_score(aggregate)
    pump = pump_risk_details(aggregate, market_data, market_score)
    pump_penalty = pump["pump_risk_score"] * 0.20

    raw_score = (
        0.25 * acceleration_score
        + 0.20 * engagement_score
        + 0.15 * sentiment_score
        + 0.15 * net_conviction
        + 0.15 * market_score
        + 0.10 * discussion_score
        - pump_penalty
    )
    normalized = round(max(0.0, min(1.0, raw_score)) * 100, 2)

    return {
        "attention_acceleration": round(acceleration, 4),
        "log_attention_acceleration": round(log_acceleration, 4),
        "attention_acceleration_score": acceleration_score,
        "engagement_quality_score": engagement_score,
        "sentiment_score": sentiment_score,
        "net_conviction_score": net_conviction,
        "market_confirmation_score": market_score,
        "discussion_quality_score": discussion_score,
        "bullish_attention_score": aggregate.bullish_attention_score,
        "bearish_attention_score": aggregate.bearish_attention_score,
        "net_positioning_score": aggregate.net_positioning_score,
        "pump_risk_penalty": round(pump_penalty, 4),
        "raw_score_0_to_1": round(raw_score, 4),
        "final_score": normalized,
        "formula": "0.25*attention_acceleration_score + 0.20*engagement_quality_score + 0.15*sentiment_score + 0.15*net_conviction_score + 0.15*market_confirmation_score + 0.10*discussion_quality_score - pump_risk_penalty",
    }


def calculate_final_score(
    aggregate: TickerAggregate,
    market_data: MarketData,
    baseline: dict[str, float] | None = None,
) -> float:
    """Calculate an explainable 0-100 score from quality signals and risk."""

    return float(score_breakdown(aggregate, market_data, baseline)["final_score"])


def recommendation_type(
    final_score: float,
    pump_risk_score: float,
    attention_acceleration: float,
    dominant_type: str,
    market_score: float,
    bullish_score: float,
) -> str:
    """Classify the ticker recommendation bucket."""

    if pump_risk_score >= 0.65:
        return "High-risk pump"
    if final_score < 25 or (pump_risk_score >= 0.45 and market_score < 0.3):
        return "Avoid / too noisy"
    if dominant_type == "Earnings":
        return "Earnings chatter"
    if attention_acceleration >= 2.5 and bullish_score >= 0.35:
        return "Possible squeeze"
    if final_score >= 55 and market_score >= 0.5:
        return "Momentum setup"
    return "Watchlist"


def build_summary(
    aggregate: TickerAggregate,
    recommendation: str,
    attention_acceleration: float,
    pump_risk_score: float,
) -> str:
    """Produce a compact human-readable explanation for a ranked ticker."""

    sentiment = aggregate.avg_sentiment
    if sentiment >= 0.25:
        sentiment_label = "positive sentiment"
    elif sentiment <= -0.25:
        sentiment_label = "negative sentiment"
    else:
        sentiment_label = "mixed sentiment"

    return (
        f"{recommendation}: {aggregate.dominant_post_type} led discussion with "
        f"{sentiment_label}, {attention_acceleration:.2f}x mention acceleration, "
        f"and pump risk {pump_risk_score:.2f}."
    )


def rank_tickers(
    aggregates: dict[str, TickerAggregate],
    market_data_by_ticker: dict[str, MarketData],
    limit: int = 15,
    generated_at: str | None = None,
    baselines: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Rank valid tickers and return JSON-serializable result rows."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    baselines = baselines or {}
    rows: list[dict[str, Any]] = []

    for ticker, aggregate in aggregates.items():
        market_data = market_data_by_ticker.get(ticker, MarketData(valid=False))
        if not market_data.valid:
            continue

        baseline = baselines.get(ticker, {})
        seven_day_avg_mentions = float(baseline.get("seven_day_avg_mentions", 0.0) or 0.0)
        attention_acceleration = aggregate.mention_count / max(seven_day_avg_mentions, 1)
        details = risk_details(market_data)
        risk_flag = str(details["risk_flag"])
        breakdown = score_breakdown(aggregate, market_data, baseline)
        market_score = float(breakdown["market_confirmation_score"])
        pump = pump_risk_details(aggregate, market_data, market_score)
        recommendation = recommendation_type(
            breakdown["final_score"],
            pump["pump_risk_score"],
            attention_acceleration,
            aggregate.dominant_post_type,
            market_score,
            aggregate.bullish_conviction_score,
        )
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
                "post_type": source.get("post_type"),
            }
            for source in top_sources
        ]

        rows.append(
            {
                "ticker": ticker,
                "final_score": breakdown["final_score"],
                "recommendation_type": recommendation,
                "risk_flag": risk_flag,
                "risk_explanation": pump["risk_explanation"],
                "mention_count": aggregate.mention_count,
                "weighted_mention_count": round(aggregate.weighted_mention_count, 2),
                "unique_posts": aggregate.unique_posts,
                "unique_subreddits": aggregate.unique_subreddits,
                "weighted_unique_posts": round(aggregate.weighted_unique_posts, 2),
                "seven_day_avg_mentions": round(seven_day_avg_mentions, 4),
                "attention_acceleration": round(attention_acceleration, 4),
                "avg_sentiment": aggregate.avg_sentiment,
                "bullish_conviction_score": aggregate.bullish_conviction_score,
                "bearish_conviction_score": aggregate.bearish_conviction_score,
                "net_conviction_score": aggregate.net_conviction_score,
                "market_confirmation_score": market_score,
                "pump_risk_score": pump["pump_risk_score"],
                "latest_price": market_data.latest_price,
                "market_cap": market_data.market_cap,
                "avg_volume": market_data.avg_volume,
                "one_day_return": market_data.one_day_return,
                "five_day_return": market_data.five_day_return,
                "relative_volume": market_data.relative_volume,
                "above_20_day_high": market_data.above_20_day_high,
                "dominant_post_type": aggregate.dominant_post_type,
                "post_type_weight_avg": aggregate.post_type_weight_avg,
                "risk_reasons": details["risk_reasons"],
                "risk_thresholds": details["risk_thresholds"],
                "score_breakdown": breakdown,
                "summary": build_summary(
                    aggregate,
                    recommendation,
                    attention_acceleration,
                    pump["pump_risk_score"],
                ),
                "top_sources": top_sources,
                "generated_at": generated_at,
            }
        )

    rows.sort(key=lambda row: row["final_score"], reverse=True)
    for rank, row in enumerate(rows[:limit], start=1):
        row["rank"] = rank

    return rows[:limit]
