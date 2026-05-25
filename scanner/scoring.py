"""Aggregation and ranking logic for ticker mentions."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scanner.alerts import generate_alerts
from scanner.conviction import conviction_scores
from scanner.disagreement import analyze_disagreement, disagreement_summary_phrase
from scanner.filters import evaluate_hard_filter
from scanner.peers import apply_peer_context
from scanner.spam_detection import analyze_spam
from scanner.watch_reasons import build_watch_reasons
from scanner.history import (
    attention_acceleration_score,
    build_historical_trends,
    build_sparkline_payload,
    catalyst_type_label,
    smoothed_attention_acceleration,
)
from scanner.market_data import MarketData
from scanner.narrative_extraction import FALLBACK_NARRATIVE, build_narrative_summary, extract_ticker_narrative
from scanner.post_classifier import dominant_post_type as choose_dominant_post_type
from scanner.subreddit_weights import (
    corroboration_factor,
    compute_subreddit_metrics,
    subreddit_weight,
)
from scanner.post_classifier import classify_post, post_type_weight
from scanner.sentiment import score_post_sentiment
from scanner.ticker_extractor import extract_tickers_from_post

RECENCY_WINDOW_DAYS = 7
RECENCY_WEIGHTS = (1.0, 0.85, 0.70, 0.55, 0.40, 0.25, 0.10)
ROCKET_TERMS = ("🚀", "🌕", "moon", "mooning", "lambo", "tendies")
ANALYST_TARGET_TERMS = (
    "price target",
    " pt ",
    "analyst",
    "upgrade",
    "downgrade",
    "outperform",
    "overweight",
    "underweight",
    "raised target",
    "lowered target",
    "consensus",
    "street target",
)
AI_CATALYST_TERMS = (
    " ai ",
    "artificial intelligence",
    "openai",
    "chatgpt",
    "llm",
    "large language model",
    "machine learning",
    "data center",
    "gpu demand",
    "inference",
    "generative ai",
)
CATALYST_TYPE_WEIGHTS = {
    "Earnings": 1.0,
    "News": 0.85,
    "DD": 0.8,
    "Options": 0.55,
    "Other": 0.45,
    "YOLO": 0.25,
    "Meme": 0.15,
    "Question": 0.2,
}
CONFIDENCE_LABEL_HIGH = 0.65
CONFIDENCE_LABEL_MEDIUM = 0.40
PENNY_STOCK_PRICE_LT = 2.0
EXTREME_LOW_AVG_VOLUME_LT = 150_000
MICROCAP_MARKET_CAP_LT = 100_000_000


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
    hype_count: int = 0
    max_repeated_mentions: int = 0
    low_quality_mentions: int = 0
    authors: set[str] = field(default_factory=set)
    analyst_target_scores: list[float] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unique_posts(self) -> int:
        return len(self.post_ids)

    @property
    def unique_subreddits(self) -> int:
        return len(self.subreddits)

    @property
    def unique_users(self) -> int:
        return len(self.authors)

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


def _term_hits(text: str, terms: tuple[str, ...]) -> int:
    lowered = f" {text.lower()} "
    return sum(1 for term in terms if term in lowered)


def analyst_target_score_from_text(*parts: Any) -> float:
    """Score analyst/upside language from 0 to 1."""

    hits = _term_hits(" ".join(str(part or "") for part in parts), ANALYST_TARGET_TERMS)
    return round(min(1.0, hits / 3), 4)


def has_ai_catalyst(*parts: Any) -> bool:
    """Return whether discussion references AI-related catalyst language."""

    return _term_hits(" ".join(str(part or "") for part in parts), AI_CATALYST_TERMS) > 0


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
        author = str(post.get("author") or "").strip()
        sentiment = score_post_sentiment(post.get("title"), post.get("selftext"), comments)
        post_analyst_score = analyst_target_score_from_text(
            post.get("title"), post.get("selftext"), " ".join(comments)
        )
        score = int(post.get("score") or 0)
        num_comments = int(post.get("num_comments") or 0)
        subreddit = str(post.get("subreddit") or "")
        post_type = classify_post(post.get("title"), post.get("selftext"), comments)
        type_weight = post_type_weight(post_type)
        conviction = conviction_scores(post.get("title"), post.get("selftext"), comments)
        hype = _hype_count(post.get("title"), post.get("selftext"), " ".join(comments))
        is_low_quality_context = post_type in {"Meme", "Question", "YOLO"} and score < 25 and num_comments < 15

        for ticker, count in mention_counts.items():
            aggregate = aggregates.setdefault(ticker, TickerAggregate(ticker=ticker))
            aggregate.mention_count += count
            aggregate.weighted_mention_count += count * weight
            aggregate.weighted_unique_posts += weight
            aggregate.post_ids.add(post_id)
            if author:
                aggregate.authors.add(author)
            aggregate.analyst_target_scores.append(post_analyst_score)
            if subreddit:
                aggregate.subreddits.add(subreddit)
            aggregate.total_upvotes += score
            aggregate.comment_volume += num_comments
            aggregate.sentiment_scores.append(sentiment)
            aggregate.post_types.append(post_type)
            aggregate.post_type_weights.append(type_weight)
            aggregate.bullish_scores.append(conviction["bullish_conviction_score"])
            aggregate.bearish_scores.append(conviction["bearish_conviction_score"])
            aggregate.hype_count += hype
            aggregate.max_repeated_mentions = max(aggregate.max_repeated_mentions, count)
            if count == 1 and is_low_quality_context:
                aggregate.low_quality_mentions += 1
            comments_excerpt = " ".join(str(c) for c in comments[:4])[:600]
            aggregate.sources.append(
                {
                    "subreddit": subreddit,
                    "title": post.get("title"),
                    "selftext": post.get("selftext"),
                    "comments_excerpt": comments_excerpt,
                    "permalink": post.get("permalink"),
                    "score": score,
                    "created_utc": post.get("created_utc"),
                    "recency_weight": round(weight, 2),
                    "post_type": post_type,
                    "subreddit_weight": round(subreddit_weight(subreddit), 2),
                    "author": author or None,
                }
            )
    return aggregates


def risk_details(market_data: MarketData) -> dict[str, Any]:
    """Return investability risk flag based on liquidity and penny-stock profile only.

    Volatility and market cap alone do not increase risk. High flags are reserved for
    clearly uninvestable micro-liquidity or sub-$2 penny profiles.
    """

    thresholds = {
        "penny_stock_price_lt": PENNY_STOCK_PRICE_LT,
        "extreme_low_avg_volume_lt": EXTREME_LOW_AVG_VOLUME_LT,
        "liquid_avg_volume_gte": 2_000_000,
        "liquid_market_cap_gte": 10_000_000_000,
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

    if latest_price is not None and latest_price < PENNY_STOCK_PRICE_LT:
        reasons.append("Sub-$2 share price: treated as a low-quality penny profile.")
    if avg_volume is not None and avg_volume < EXTREME_LOW_AVG_VOLUME_LT:
        reasons.append("Extremely low liquidity: average volume is below 150,000 shares.")

    if reasons:
        return {"risk_flag": "high", "risk_reasons": reasons, "risk_thresholds": thresholds}

    if (
        latest_price is not None
        and latest_price >= 5
        and avg_volume is not None
        and avg_volume >= thresholds["liquid_avg_volume_gte"]
        and market_cap is not None
        and market_cap >= thresholds["liquid_market_cap_gte"]
    ):
        return {
            "risk_flag": "low",
            "risk_reasons": [
                "Large, liquid profile suitable for size: strong average volume and market cap."
            ],
            "risk_thresholds": thresholds,
        }

    return {
        "risk_flag": "medium",
        "risk_reasons": [
            "Investable profile: volatile or smaller-cap names are allowed when liquidity is reasonable."
        ],
        "risk_thresholds": thresholds,
    }


def determine_risk_flag(market_data: MarketData) -> str:
    """Classify ticker risk from simple market-data heuristics."""

    return str(risk_details(market_data)["risk_flag"])


def _average_subreddit_weight(sources: list[dict[str, Any]]) -> float:
    weights = [
        float(source.get("subreddit_weight") or subreddit_weight(source.get("subreddit")))
        for source in sources
        if source.get("subreddit")
    ]
    if not weights:
        return 1.0
    return sum(weights) / len(weights)


def engagement_quality_score(aggregate: TickerAggregate) -> float:
    """Score engagement quality from 0 to 1 using upvotes/comments and post quality."""

    engagement = math.log1p(max(aggregate.total_upvotes, 0)) / math.log1p(10_000)
    comments = math.log1p(max(aggregate.comment_volume, 0)) / math.log1p(2_000)
    type_quality = min(1.0, aggregate.post_type_weight_avg / 1.5)
    score = 0.45 * engagement + 0.30 * comments + 0.25 * type_quality
    subreddit_factor = min(1.12, _average_subreddit_weight(aggregate.sources) / 1.0)
    return round(max(0.0, min(1.0, score * subreddit_factor)), 4)


def discussion_quality_score(
    aggregate: TickerAggregate,
    *,
    subreddit_metrics: dict[str, Any] | None = None,
    narrative_confidence_score: float = 0.0,
) -> float:
    """Score discussion quality from 0 to 1 using engagement and substantive post mix."""

    if not aggregate.post_types:
        return 0.0

    metrics = subreddit_metrics or compute_subreddit_metrics(aggregate.sources)
    engagement = engagement_quality_score(aggregate)
    total = len(aggregate.post_types)
    substantive_share = sum(1 for item in aggregate.post_types if item in {"DD", "News", "Earnings"}) / total
    noise_share = sum(1 for item in aggregate.post_types if item in {"Meme", "YOLO", "Question"}) / total
    score = (
        0.42 * engagement
        + 0.30 * substantive_share
        + 0.13 * (1.0 - noise_share)
        + 0.10 * float(metrics.get("subreddit_weighted_score") or 0.0)
        + corroboration_factor(metrics)
        + 0.05 * narrative_confidence_score
    )
    return round(max(0.0, min(1.0, score)), 4)


def analyst_target_score(aggregate: TickerAggregate) -> float:
    """Aggregate analyst/upside language strength from 0 to 1."""

    if not aggregate.analyst_target_scores:
        return 0.0
    return round(max(aggregate.analyst_target_scores), 4)


def catalyst_confidence_score(aggregate: TickerAggregate) -> float:
    """Score catalyst strength from dominant and weighted post-type mix."""

    if not aggregate.post_types:
        return 0.0

    weighted = [
        CATALYST_TYPE_WEIGHTS.get(post_type, CATALYST_TYPE_WEIGHTS["Other"])
        for post_type in aggregate.post_types
    ]
    dominant_weight = CATALYST_TYPE_WEIGHTS.get(
        aggregate.dominant_post_type, CATALYST_TYPE_WEIGHTS["Other"]
    )
    average_weight = sum(weighted) / len(weighted)
    return round(max(0.0, min(1.0, 0.55 * dominant_weight + 0.45 * average_weight)), 4)


def unique_users_score(aggregate: TickerAggregate) -> float:
    """Score author breadth from 0 to 1."""

    unique_users = aggregate.unique_users
    unique_posts = aggregate.unique_posts
    if unique_users <= 0:
        return 0.0

    diversity = unique_users / max(unique_posts, 1)
    breadth = min(1.0, unique_users / 5)
    return round(max(0.0, min(1.0, 0.55 * diversity + 0.45 * breadth)), 4)


def aggregate_has_ai_catalyst(aggregate: TickerAggregate) -> bool:
    """Return whether any source post references AI catalyst language."""

    for source in aggregate.sources:
        if has_ai_catalyst(source.get("title")):
            return True
    return False


def low_pump_risk_score(pump_risk_score: float) -> float:
    """Invert pump risk into a confidence-friendly 0-1 score."""

    return round(max(0.0, min(1.0, 1.0 - pump_risk_score)), 4)


def signal_confidence_score(
    *,
    subreddit_spread: float,
    discussion_quality: float,
    analyst_target: float,
    market_confirmation: float,
    pump_risk: float,
    unique_users: float,
    catalyst_confidence: float,
    narrative_confidence_score: float = 0.0,
    disagreement_score: float = 0.0,
    spam_composite_score: float = 0.0,
) -> float:
    """Combine signal quality inputs into a 0-1 confidence score."""

    low_pump = low_pump_risk_score(pump_risk)
    consensus_factor = max(0.0, 1.0 - disagreement_score * 0.35)
    spam_penalty = min(0.12, spam_composite_score * 0.12)
    raw = (
        0.11 * subreddit_spread
        + 0.16 * discussion_quality
        + 0.12 * analyst_target
        + 0.15 * market_confirmation
        + 0.12 * low_pump
        + 0.10 * unique_users
        + 0.09 * catalyst_confidence
        + 0.07 * narrative_confidence_score
        + 0.08 * consensus_factor
        - spam_penalty
    )
    return round(max(0.0, min(1.0, raw)), 4)


def signal_confidence_label(confidence_score: float) -> str:
    """Map a confidence score to LOW, MEDIUM, or HIGH."""

    if confidence_score >= CONFIDENCE_LABEL_HIGH:
        return "HIGH"
    if confidence_score >= CONFIDENCE_LABEL_MEDIUM:
        return "MEDIUM"
    return "LOW"


def normalized_sentiment_score(avg_sentiment: float) -> float:
    return round(max(0.0, min(1.0, (avg_sentiment + 1) / 2)), 4)


def market_confirmation_score(market_data: MarketData) -> float:
    """Score market confirmation from 0 to 1, rewarding momentum and participation."""

    if not market_data.valid:
        return 0.0

    score = 0.25
    five_day = market_data.five_day_return
    if five_day is not None:
        if five_day >= 0.10:
            score += 0.30
        elif five_day >= 0.04:
            score += 0.22
        elif five_day > 0:
            score += 0.14
        elif five_day > -0.06:
            score += 0.06
        else:
            score -= 0.04

    one_day = market_data.one_day_return
    if one_day is not None:
        if one_day >= 0.04:
            score += 0.12
        elif one_day > 0:
            score += 0.06
        elif one_day > -0.04:
            score += 0.02

    relative_volume = market_data.relative_volume
    if relative_volume is not None:
        if relative_volume >= 2.0:
            score += 0.28
        elif relative_volume >= 1.3:
            score += 0.18
        elif relative_volume >= 1.0:
            score += 0.08

    if market_data.above_20_day_high:
        score += 0.22

    if market_data.avg_volume is not None and market_data.avg_volume < EXTREME_LOW_AVG_VOLUME_LT:
        score -= 0.12

    return round(max(0.0, min(1.0, score)), 4)


def subreddit_spread_score(unique_subreddits: int) -> float:
    if unique_subreddits <= 0:
        return 0.0
    return round(min(1.0, unique_subreddits * 0.25), 4)


def pump_risk_details(
    aggregate: TickerAggregate,
    market_data: MarketData,
    market_score: float,
    discussion_quality: float = 0.0,
    spam_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score low-quality speculative activity, not volatility or size alone."""

    spam_metrics = spam_metrics or {}
    components: list[float] = []
    reasons: list[str] = []

    hype_component = min(1.0, aggregate.hype_count / 8)
    if hype_component >= 0.25:
        reasons.append("Heavy rocket/moon spam language detected.")
    components.append(hype_component)

    repeated_component = min(1.0, max(0, aggregate.max_repeated_mentions - 3) / 7)
    if repeated_component > 0:
        reasons.append("Ticker is repeated many times within the same post/comment context.")
    components.append(repeated_component)

    meme_yolo_share = 0.0
    if aggregate.post_types:
        meme_yolo_share = sum(1 for item in aggregate.post_types if item in {"Meme", "YOLO"}) / len(
            aggregate.post_types
        )
    components.append(meme_yolo_share)
    if meme_yolo_share >= 0.5:
        reasons.append("Most discussion is meme/YOLO driven.")

    if market_data.latest_price is not None and market_data.latest_price < PENNY_STOCK_PRICE_LT:
        components.append(0.85)
        reasons.append("Sub-$2 penny profile with elevated low-quality speculation risk.")
    if market_data.avg_volume is not None and market_data.avg_volume < EXTREME_LOW_AVG_VOLUME_LT:
        components.append(0.8)
        reasons.append("Extremely low liquidity increases pump/manipulation risk.")

    microcap = market_data.market_cap is not None and market_data.market_cap < MICROCAP_MARKET_CAP_LT
    if microcap and discussion_quality < 0.4 and meme_yolo_share >= 0.4:
        components.append(0.75)
        reasons.append("Microcap with weak discussion quality and meme-heavy hype.")

    if meme_yolo_share >= 0.65 and discussion_quality < 0.35:
        components.append(0.7)
        reasons.append("Low-quality meme-only hype with little substantive discussion.")

    if aggregate.avg_sentiment >= 0.45 and market_score < 0.30 and meme_yolo_share >= 0.35:
        components.append(0.45)
        reasons.append("Bullish Reddit hype is running ahead of market confirmation.")

    if aggregate.low_quality_mentions and aggregate.mention_count <= 2:
        components.append(0.4)
        reasons.append("Ticker appears only in low-quality one-off contexts.")

    spam_composite = float(spam_metrics.get("spam_composite_score") or 0)
    if spam_composite >= 0.35:
        components.append(min(1.0, spam_composite))
        spam_reason = str(spam_metrics.get("spam_risk_explanation") or "").strip()
        if spam_reason:
            reasons.append(spam_reason)

    score = sum(components) / len(components) if components else 0.0
    return {
        "pump_risk_score": round(max(0.0, min(1.0, score)), 4),
        "risk_explanation": " ".join(reasons) if reasons else "No major low-quality pump signals detected.",
    }


def score_breakdown(
    aggregate: TickerAggregate,
    market_data: MarketData,
    baseline: dict[str, float] | None = None,
    mentions_7d: list[float] | None = None,
    spam_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate component scores used to produce final_score."""

    baseline = baseline or {}
    seven_day_avg_mentions = float(baseline.get("seven_day_avg_mentions", 0.0) or 0.0)
    if mentions_7d:
        attention_acceleration = smoothed_attention_acceleration(mentions_7d)
    else:
        attention_acceleration = aggregate.mention_count / max(seven_day_avg_mentions, 1)
    acceleration_score = attention_acceleration_score(attention_acceleration)
    engagement_score = engagement_quality_score(aggregate)
    sentiment_score = normalized_sentiment_score(aggregate.avg_sentiment)
    net_conviction = aggregate.net_conviction_score
    market_score = market_confirmation_score(market_data)
    spread_score = subreddit_spread_score(aggregate.unique_subreddits)
    discussion_quality = discussion_quality_score(aggregate)
    pump = pump_risk_details(
        aggregate,
        market_data,
        market_score,
        discussion_quality,
        spam_metrics=spam_metrics,
    )
    pump_penalty = pump["pump_risk_score"] * 0.20

    raw_score = (
        0.25 * acceleration_score
        + 0.20 * engagement_score
        + 0.15 * sentiment_score
        + 0.15 * net_conviction
        + 0.15 * market_score
        + 0.10 * spread_score
        - pump_penalty
    )
    normalized = round(max(0.0, min(1.0, raw_score)) * 100, 2)

    return {
        "attention_acceleration": round(attention_acceleration, 4),
        "attention_acceleration_score": acceleration_score,
        "engagement_quality_score": engagement_score,
        "sentiment_score": sentiment_score,
        "net_conviction_score": net_conviction,
        "market_confirmation_score": market_score,
        "subreddit_spread_score": spread_score,
        "pump_risk_penalty": round(pump_penalty, 4),
        "raw_score_0_to_1": round(raw_score, 4),
        "final_score": normalized,
        "formula": "0.25*attention_acceleration + 0.20*engagement_quality + 0.15*sentiment + 0.15*net_conviction + 0.15*market_confirmation + 0.10*subreddit_spread - pump_risk_penalty",
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
    *,
    bearish_score: float = 0.0,
    avg_sentiment: float = 0.0,
    discussion_quality: float = 0.0,
    analyst_target: float = 0.0,
    catalyst_confidence: float = 0.0,
    acceleration_score: float = 0.0,
    has_ai: bool = False,
    hype_count: int = 0,
    latest_price: float | None = None,
    avg_volume: int | None = None,
) -> str:
    """Classify the ticker recommendation bucket."""

    illiquid_penny = (
        latest_price is not None
        and latest_price < PENNY_STOCK_PRICE_LT
        and avg_volume is not None
        and avg_volume < EXTREME_LOW_AVG_VOLUME_LT
    )
    if pump_risk_score >= 0.68 and (discussion_quality < 0.35 or illiquid_penny):
        return "Low-quality pump"
    if final_score < 25 or (pump_risk_score >= 0.55 and discussion_quality < 0.3):
        return "Avoid / too noisy"
    if analyst_target >= 0.5 and discussion_quality >= 0.6:
        return "Analyst upside watch"
    if dominant_type == "Earnings" and market_score >= 0.5 and catalyst_confidence >= 0.55:
        return "High-upside catalyst trade"
    if has_ai and attention_acceleration >= 2.0 and acceleration_score >= 0.6:
        return "High-upside catalyst trade"
    if bearish_score >= 0.35 and (avg_sentiment <= -0.15 or bearish_score > bullish_score):
        return "Panic selloff"
    if discussion_quality >= 0.6 and pump_risk_score <= 0.35 and hype_count <= 2:
        return "Institutional-style accumulation"
    if attention_acceleration >= 2.5 and pump_risk_score < 0.5 and discussion_quality >= 0.4:
        return "Strong retail acceleration"
    if final_score >= 55 and market_score >= 0.55 and attention_acceleration >= 1.5:
        return "Volatile momentum setup"
    if (
        final_score >= 45
        and attention_acceleration >= 1.2
        and discussion_quality >= 0.4
        and pump_risk_score < 0.5
    ):
        return "Aggressive growth watch"
    if attention_acceleration >= 2.5 and pump_risk_score >= 0.5 and discussion_quality < 0.4:
        return "Low-quality pump"
    if avg_sentiment <= -0.1 and discussion_quality >= 0.4 and pump_risk_score <= 0.45:
        return "Contrarian watchlist"
    return "Watchlist"


def strength_tier(score: float, *, invert: bool = False) -> str:
    """Map a 0-1 score to Weak, Moderate, or Strong."""

    value = 1.0 - score if invert else score
    if value >= 0.65:
        return "Strong"
    if value >= 0.4:
        return "Moderate"
    return "Weak"


def build_signal_summaries(
    *,
    attention_acceleration_score: float,
    discussion_quality: float,
    market_confirmation: float,
    pump_risk: float,
    analyst_target_upside_pct: float | None,
    reddit_analyst_language: float,
) -> dict[str, str]:
    """Return compact signal summary tiers for dashboard display."""

    if analyst_target_upside_pct is not None:
        if analyst_target_upside_pct >= 0.10:
            analyst_outlook = "Strong"
        elif analyst_target_upside_pct >= -0.03:
            analyst_outlook = "Moderate"
        else:
            analyst_outlook = "Weak"
    elif reddit_analyst_language >= 0.5:
        analyst_outlook = "Moderate"
    else:
        analyst_outlook = "Weak"

    return {
        "retail_attention": strength_tier(attention_acceleration_score),
        "discussion_quality": strength_tier(discussion_quality),
        "market_confirmation": strength_tier(market_confirmation),
        "speculation_risk": strength_tier(pump_risk, invert=False),
        "analyst_outlook": analyst_outlook,
    }


def build_summary(
    aggregate: TickerAggregate,
    recommendation: str,
    attention_acceleration: float,
    pump_risk_score: float,
    *,
    catalyst_type: str = "Other",
    discussion_quality: float = 0.0,
    market_score: float = 0.0,
    analyst_target_upside_pct: float | None = None,
    has_ai: bool = False,
    narrative: dict[str, Any] | None = None,
    disagreement_phrase: str = "",
) -> str:
    """Produce a narrative-aware summary for a ranked ticker."""

    accel_phrase = "picked up sharply" if attention_acceleration >= 2.5 else (
        "accelerated" if attention_acceleration >= 1.5 else "inched higher"
    )

    if pump_risk_score >= 0.55 and discussion_quality < 0.4:
        quality_phrase = "while low-quality hype and spammy tone dominated the thread"
    elif pump_risk_score >= 0.45:
        quality_phrase = "with some speculative hype mixed into the discussion"
    elif discussion_quality >= 0.6:
        quality_phrase = "and the conversation looked relatively substantive"
    else:
        quality_phrase = "with a mixed but still investable conversation"

    market_phrase = (
        "Momentum and volume are confirming the narrative."
        if market_score >= 0.6
        else "Attention is building, but market confirmation is only partial."
        if market_score >= 0.35
        else "Retail attention is rising faster than market confirmation."
    )

    street_phrase = ""
    if analyst_target_upside_pct is not None:
        if analyst_target_upside_pct >= 0.08:
            street_phrase = (
                f" Street targets still imply about {analyst_target_upside_pct * 100:.0f}% upside, "
                "which supports the Reddit narrative."
            )
        elif analyst_target_upside_pct <= -0.08:
            street_phrase = (
                f" Consensus targets sit roughly {abs(analyst_target_upside_pct) * 100:.0f}% "
                "below the current price, which contrasts with the bullish Reddit tone."
            )

    narrative = narrative or {}
    mixed = f" {disagreement_phrase}" if disagreement_phrase else ""
    if narrative.get("primary_narrative") and narrative.get("primary_narrative") != FALLBACK_NARRATIVE:
        text = build_narrative_summary(
            aggregate.ticker,
            narrative,
            attention_phrase=accel_phrase,
            quality_phrase=quality_phrase,
            market_phrase=market_phrase,
            street_phrase=street_phrase,
        )
        return f"{text}{mixed}".strip()

    catalyst = catalyst_type or aggregate.dominant_post_type or "Other"
    driver = "earnings and guidance" if catalyst == "Earnings" else f"{catalyst.lower()} discussion"
    return (
        f"{aggregate.ticker} discussion {accel_phrase} as users focused on {driver}, {quality_phrase}. "
        f"{market_phrase}{street_phrase}{mixed}"
    ).strip()


def _mentions_series_for_ticker(
    ticker: str,
    snapshots: list[tuple[str, list[dict[str, Any]]]],
    current_mentions: float,
) -> list[float]:
    """Build a 7-day mention series ending with the current run's mention count."""

    symbol = ticker.upper()
    series: list[float] = []
    for index, (_day, rows) in enumerate(snapshots):
        if index == len(snapshots) - 1:
            series.append(float(current_mentions))
            continue
        row = next(
            (item for item in rows if str(item.get("ticker") or "").upper() == symbol),
            None,
        )
        try:
            series.append(float(row.get("mention_count") or 0) if row else 0.0)
        except (TypeError, ValueError):
            series.append(0.0)
    return series


def _build_result_row(
    ticker: str,
    aggregate: TickerAggregate,
    market_data: MarketData,
    *,
    generated_at: str,
    baselines: dict[str, dict[str, float]],
    history_snapshots: list[tuple[str, list[dict[str, Any]]]] | None,
) -> dict[str, Any]:
    """Build a full scanner result row before hard-filtering and ranking."""

    baseline = baselines.get(ticker, {})
    seven_day_avg_mentions = float(baseline.get("seven_day_avg_mentions", 0.0) or 0.0)
    mentions_7d = (
        _mentions_series_for_ticker(ticker, history_snapshots, aggregate.mention_count)
        if history_snapshots
        else None
    )
    details = risk_details(market_data)
    risk_flag = str(details["risk_flag"])
    spam_metrics = analyze_spam(aggregate)
    breakdown = score_breakdown(
        aggregate,
        market_data,
        baseline,
        mentions_7d=mentions_7d,
        spam_metrics=spam_metrics,
    )
    attention_acceleration = float(
        breakdown.get("attention_acceleration")
        or (aggregate.mention_count / max(seven_day_avg_mentions, 1))
    )
    market_score = float(breakdown["market_confirmation_score"])
    spread_score = float(breakdown["subreddit_spread_score"])
    subreddit_metrics = compute_subreddit_metrics(aggregate.sources)
    disagreement = analyze_disagreement(aggregate)
    narrative = extract_ticker_narrative(
        ticker,
        aggregate.sources,
        post_types=aggregate.post_types,
        unique_subreddits=aggregate.unique_subreddits,
    )
    discussion_quality = discussion_quality_score(
        aggregate,
        subreddit_metrics=subreddit_metrics,
        narrative_confidence_score=float(narrative.get("narrative_confidence_score") or 0.0),
    )
    pump = pump_risk_details(
        aggregate,
        market_data,
        market_score,
        discussion_quality,
        spam_metrics=spam_metrics,
    )
    analyst_target = analyst_target_score(aggregate)
    catalyst_confidence = catalyst_confidence_score(aggregate)
    unique_users = unique_users_score(aggregate)
    confidence_score = signal_confidence_score(
        subreddit_spread=spread_score,
        discussion_quality=discussion_quality,
        analyst_target=analyst_target,
        market_confirmation=market_score,
        pump_risk=pump["pump_risk_score"],
        unique_users=unique_users,
        catalyst_confidence=catalyst_confidence,
        narrative_confidence_score=float(narrative.get("narrative_confidence_score") or 0.0),
        disagreement_score=float(disagreement.get("disagreement_score") or 0.0),
        spam_composite_score=float(spam_metrics.get("spam_composite_score") or 0.0),
    )
    confidence_label = signal_confidence_label(confidence_score)
    recommendation = recommendation_type(
        breakdown["final_score"],
        pump["pump_risk_score"],
        attention_acceleration,
        aggregate.dominant_post_type,
        market_score,
        aggregate.bullish_conviction_score,
        bearish_score=aggregate.bearish_conviction_score,
        avg_sentiment=aggregate.avg_sentiment,
        discussion_quality=discussion_quality,
        analyst_target=analyst_target,
        catalyst_confidence=catalyst_confidence,
        acceleration_score=float(breakdown["attention_acceleration_score"]),
        has_ai=aggregate_has_ai_catalyst(aggregate),
        hype_count=aggregate.hype_count,
        latest_price=market_data.latest_price,
        avg_volume=market_data.avg_volume,
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

    if history_snapshots:
        historical_trends = build_historical_trends(
            ticker,
            history_snapshots,
            current_mentions=float(aggregate.mention_count),
            current_sentiment=float(aggregate.avg_sentiment),
            current_score=float(breakdown["final_score"]),
            current_analyst_target=float(analyst_target),
        )
    else:
        historical_trends = {
            "mentions_7d": [0.0] * 6 + [float(aggregate.mention_count)],
            "sentiment_7d": [0.0] * 6 + [float(aggregate.avg_sentiment)],
            "score_7d": [0.0] * 6 + [float(breakdown["final_score"])],
            "analyst_target_upside_7d": [0.0] * 6 + [float(analyst_target)],
        }
    sparklines = build_sparkline_payload(historical_trends)
    catalyst_type = catalyst_type_label(aggregate.dominant_post_type, catalyst_confidence)
    disagreement_phrase = disagreement_summary_phrase(
        consensus_label=str(disagreement.get("consensus_label") or ""),
        bullish_claims=narrative.get("bullish_claims"),
        bearish_claims=narrative.get("bearish_claims"),
        bullish_themes=narrative.get("bullish_themes"),
        bearish_themes=narrative.get("bearish_themes"),
    )
    price = market_data.latest_price
    under_15 = price is not None and float(price) < 15

    row: dict[str, Any] = {
        "ticker": ticker,
        "final_score": breakdown["final_score"],
        "signal_confidence_score": confidence_score,
        "signal_confidence_label": confidence_label,
        "recommendation_type": recommendation,
        "discussion_quality_score": discussion_quality,
        "analyst_target_score": analyst_target,
        "catalyst_confidence_score": catalyst_confidence,
        "unique_users_score": unique_users,
        "unique_users": aggregate.unique_users,
        "catalyst_type": catalyst_type,
        "subreddit_groups_detected": subreddit_metrics.get("subreddit_groups_detected", []),
        "top_signal_subreddits": subreddit_metrics.get("top_signal_subreddits", []),
        "noisy_subreddit_exposure": subreddit_metrics.get("noisy_subreddit_exposure", 0.0),
        "subreddit_weighted_score": subreddit_metrics.get("subreddit_weighted_score", 0.0),
        "duplicate_content_score": spam_metrics.get("duplicate_content_score"),
        "spam_cluster_score": spam_metrics.get("spam_cluster_score"),
        "repeated_ticker_score": spam_metrics.get("repeated_ticker_score"),
        "spam_risk_explanation": spam_metrics.get("spam_risk_explanation"),
        "bullish_evidence_count": disagreement.get("bullish_evidence_count"),
        "bearish_evidence_count": disagreement.get("bearish_evidence_count"),
        "disagreement_score": disagreement.get("disagreement_score"),
        "consensus_label": disagreement.get("consensus_label"),
        "primary_narrative": narrative.get("primary_narrative"),
        "primary_claim": narrative.get("primary_claim"),
        "bullish_themes": narrative.get("bullish_themes", []),
        "bearish_themes": narrative.get("bearish_themes", []),
        "neutral_themes": narrative.get("neutral_themes", []),
        "bullish_claims": narrative.get("bullish_claims", []),
        "bearish_claims": narrative.get("bearish_claims", []),
        "claims": narrative.get("claims", []),
                "ma_direction": narrative.get("ma_direction"),
                "trading_buy_mentions_count": narrative.get("trading_buy_mentions_count", 0),
                "corporate_mna_mentions_count": narrative.get("corporate_mna_mentions_count", 0),
                "mna_detected": narrative.get("mna_detected", False),
                "mna_direction": narrative.get("mna_direction"),
                "mna_certainty": narrative.get("mna_certainty"),
                "mna_status": narrative.get("mna_status"),
                "mna_evidence_snippets": narrative.get("mna_evidence_snippets", []),
                "mna_confidence_score": narrative.get("mna_confidence_score", 0.0),
        "narrative_confidence": narrative.get("narrative_confidence"),
        "narrative_confidence_score": narrative.get("narrative_confidence_score"),
        "narrative_keywords": narrative.get("narrative_keywords", []),
        "narrative_sources_count": narrative.get("narrative_sources_count", 0),
        "evidence_snippets": narrative.get("evidence_snippets", []),
        "evidence_source_titles": narrative.get("evidence_source_titles", []),
        "evidence_subreddits": narrative.get("evidence_subreddits", []),
        "historical_trends": historical_trends,
        "sparklines": sparklines,
        "trend_dates": [day for day, _rows in history_snapshots] if history_snapshots else [],
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
        "price_at_signal": market_data.latest_price,
        "signal_score_at_signal": breakdown["final_score"],
        "under_15_flag": under_15,
        "market_cap": market_data.market_cap,
        "avg_volume": market_data.avg_volume,
        "one_day_return": market_data.one_day_return,
        "five_day_return": market_data.five_day_return,
        "relative_volume": market_data.relative_volume,
        "above_20_day_high": market_data.above_20_day_high,
        "analyst_target_mean": market_data.analyst_target_mean,
        "analyst_target_high": market_data.analyst_target_high,
        "analyst_target_low": market_data.analyst_target_low,
        "analyst_target_upside_pct": market_data.analyst_target_upside_pct,
        "dominant_post_type": aggregate.dominant_post_type,
        "subreddit_spread_score": spread_score,
        "signal_summaries": build_signal_summaries(
            attention_acceleration_score=float(breakdown["attention_acceleration_score"]),
            discussion_quality=discussion_quality,
            market_confirmation=market_score,
            pump_risk=pump["pump_risk_score"],
            analyst_target_upside_pct=market_data.analyst_target_upside_pct,
            reddit_analyst_language=analyst_target,
        ),
        "post_type_weight_avg": aggregate.post_type_weight_avg,
        "risk_reasons": details["risk_reasons"],
        "risk_thresholds": details["risk_thresholds"],
        "score_breakdown": breakdown,
        "summary": build_summary(
            aggregate,
            recommendation,
            attention_acceleration,
            pump["pump_risk_score"],
            catalyst_type=catalyst_type,
            discussion_quality=discussion_quality,
            market_score=market_score,
            analyst_target_upside_pct=market_data.analyst_target_upside_pct,
            has_ai=aggregate_has_ai_catalyst(aggregate),
            narrative=narrative,
            disagreement_phrase=disagreement_phrase,
        ),
        "top_sources": top_sources,
        "generated_at": generated_at,
        "excluded": False,
        "exclusion_reason": None,
    }
    watch_reason, caution_reason = build_watch_reasons(row)
    row["watch_reason"] = watch_reason
    row["caution_reason"] = caution_reason
    alert_payload = generate_alerts(row, history_snapshots=history_snapshots)
    row["alerts"] = alert_payload.get("alerts", [])
    row["alert_level"] = alert_payload.get("alert_level", "NONE")
    return row


def rank_tickers_with_exclusions(
    aggregates: dict[str, TickerAggregate],
    market_data_by_ticker: dict[str, MarketData],
    limit: int = 50,
    generated_at: str | None = None,
    baselines: dict[str, dict[str, float]] | None = None,
    history_snapshots: list[tuple[str, list[dict[str, Any]]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank tickers and return (ranked_rows, excluded_rows)."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    baselines = baselines or {}
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for ticker, aggregate in aggregates.items():
        market_data = market_data_by_ticker.get(ticker, MarketData(valid=False))
        if not market_data.valid:
            excluded.append(
                {
                    "ticker": ticker,
                    "excluded": True,
                    "exclusion_reason": "Invalid or missing market data.",
                    "generated_at": generated_at,
                }
            )
            continue

        row = _build_result_row(
            ticker,
            aggregate,
            market_data,
            generated_at=generated_at,
            baselines=baselines,
            history_snapshots=history_snapshots,
        )
        spam_metrics = {
            "spam_cluster_score": row.get("spam_cluster_score"),
        }
        should_exclude, reason = evaluate_hard_filter(
            ticker,
            aggregate,
            market_data,
            spam_metrics=spam_metrics,
            pump_risk_score=float(row.get("pump_risk_score") or 0),
        )
        if should_exclude:
            row["excluded"] = True
            row["exclusion_reason"] = reason
            excluded.append(row)
            continue
        candidates.append(row)

    candidates.sort(key=lambda item: float(item.get("final_score") or 0), reverse=True)
    ranked = apply_peer_context(candidates[:limit])
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked, excluded


def rank_tickers(
    aggregates: dict[str, TickerAggregate],
    market_data_by_ticker: dict[str, MarketData],
    limit: int = 50,
    generated_at: str | None = None,
    baselines: dict[str, dict[str, float]] | None = None,
    history_snapshots: list[tuple[str, list[dict[str, Any]]]] | None = None,
) -> list[dict[str, Any]]:
    """Rank valid tickers and return JSON-serializable result rows."""

    ranked, _excluded = rank_tickers_with_exclusions(
        aggregates,
        market_data_by_ticker,
        limit=limit,
        generated_at=generated_at,
        baselines=baselines,
        history_snapshots=history_snapshots,
    )
    return ranked
