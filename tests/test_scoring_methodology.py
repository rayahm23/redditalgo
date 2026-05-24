from scanner.market_data import MarketData
from scanner.scoring import (
    TickerAggregate,
    aggregate_has_ai_catalyst,
    analyst_target_score_from_text,
    build_signal_summaries,
    build_summary,
    catalyst_confidence_score,
    normalized_sentiment_score,
    recommendation_type,
    score_breakdown,
    signal_confidence_label,
    signal_confidence_score,
    strength_tier,
)
from scanner.history import smoothed_attention_acceleration


def test_normalized_sentiment_score_bounds():
    assert normalized_sentiment_score(-1.0) == 0.0
    assert normalized_sentiment_score(1.0) == 1.0
    assert normalized_sentiment_score(0.0) == 0.5


def test_score_breakdown_normalizes_final_score_to_0_100():
    aggregate = TickerAggregate(
        ticker="TSLA",
        mention_count=8,
        total_upvotes=500,
        comment_volume=80,
    )
    aggregate.post_ids.update({"a", "b"})
    aggregate.sentiment_scores.extend([0.4, 0.6])
    aggregate.post_types.extend(["DD", "News"])
    aggregate.post_type_weights.extend([1.5, 1.3])
    aggregate.bullish_scores.extend([0.5, 0.25])
    aggregate.bearish_scores.extend([0.0, 0.0])

    breakdown = score_breakdown(
        aggregate,
        MarketData(
            valid=True,
            latest_price=200,
            avg_volume=10_000_000,
            market_cap=500_000_000_000,
            one_day_return=0.02,
            five_day_return=0.03,
            relative_volume=1.4,
            above_20_day_high=True,
        ),
        mentions_7d=[1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 8.0],
    )

    assert 0 <= breakdown["raw_score_0_to_1"] <= 1
    assert 0 <= breakdown["final_score"] <= 100
    assert breakdown["attention_acceleration"] == smoothed_attention_acceleration(
        [1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 8.0]
    )


def test_catalyst_detection_and_confidence_labels():
    aggregate = TickerAggregate(ticker="NVDA")
    aggregate.post_types.extend(["News", "News", "Earnings"])
    aggregate.sources.append({"title": "Generative AI demand keeps accelerating"})

    assert aggregate_has_ai_catalyst(aggregate) is True
    assert catalyst_confidence_score(aggregate) >= 0.55
    assert analyst_target_score_from_text("Analyst upgrade with price target raised") >= 0.33

    score = signal_confidence_score(
        subreddit_spread=0.75,
        discussion_quality=0.75,
        analyst_target=0.67,
        market_confirmation=0.8,
        pump_risk=0.15,
        unique_users=0.6,
        catalyst_confidence=0.75,
    )
    assert signal_confidence_label(score) == "HIGH"


def test_build_summary_is_natural_language():
    aggregate = TickerAggregate(ticker="AMD")
    aggregate.post_types.append("Earnings")
    text = build_summary(
        aggregate,
        "Earnings momentum",
        3.0,
        0.2,
        catalyst_type="Earnings",
        discussion_quality=0.7,
        market_score=0.6,
        analyst_target_upside_pct=0.15,
    )
    assert "AMD discussion" in text
    assert "0.20" not in text
    assert "analyst target" in text.lower()


def test_build_signal_summaries_tiers():
    summaries = build_signal_summaries(
        attention_acceleration_score=0.9,
        discussion_quality=0.7,
        market_confirmation=0.5,
        pump_risk=0.2,
        analyst_target_upside_pct=0.12,
        reddit_analyst_language=0.3,
    )
    assert summaries["retail_attention"] == "Strong"
    assert summaries["speculation_risk"] == "Weak"
    assert strength_tier(0.7) == "Strong"


def test_recommendation_logic_priority_order():
    assert recommendation_type(70, 0.7, 3.0, "Meme", 0.2, 0.2) == "High-risk pump"
    assert (
        recommendation_type(
            70,
            0.2,
            1.0,
            "DD",
            0.7,
            0.4,
            discussion_quality=0.65,
            analyst_target=0.67,
        )
        == "Analyst upside watch"
    )
    assert (
        recommendation_type(
            70,
            0.2,
            1.0,
            "Earnings",
            0.6,
            0.2,
            catalyst_confidence=0.7,
        )
        == "Earnings momentum"
    )
