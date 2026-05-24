from scanner.market_data import MarketData
from scanner.scoring import (
    TickerAggregate,
    determine_risk_flag,
    market_confirmation_score,
    pump_risk_details,
    recommendation_type,
    risk_details,
)


def test_volatile_growth_names_are_investable_not_high_risk():
    """ASTS/PLTR-style profiles should not be flagged high solely on cap or volatility."""
    profile = MarketData(
        valid=True,
        latest_price=25.0,
        avg_volume=8_000_000,
        market_cap=5_000_000_000,
        five_day_return=0.12,
        relative_volume=1.8,
        above_20_day_high=True,
    )
    assert determine_risk_flag(profile) == "medium"
    assert market_confirmation_score(profile) >= 0.6


def test_sub_two_dollar_or_extreme_illiquidity_is_high_risk():
    penny = risk_details(MarketData(valid=True, latest_price=1.5, avg_volume=5_000_000, market_cap=80_000_000))
    assert penny["risk_flag"] == "high"
    illiquid = risk_details(MarketData(valid=True, latest_price=8.0, avg_volume=90_000, market_cap=200_000_000))
    assert illiquid["risk_flag"] == "high"


def test_price_between_two_and_five_is_not_automatic_high_risk():
    assert (
        determine_risk_flag(
            MarketData(valid=True, latest_price=4.5, avg_volume=2_000_000, market_cap=400_000_000)
        )
        == "medium"
    )


def test_pump_risk_targets_low_quality_not_size_alone():
    aggregate = TickerAggregate(ticker="ASTS", mention_count=6)
    aggregate.post_types.extend(["DD", "News", "Earnings"])
    aggregate.sentiment_scores.extend([0.3, 0.4])
    volatile = MarketData(valid=True, latest_price=30, avg_volume=6_000_000, market_cap=8_000_000_000)
    quality_pump = pump_risk_details(aggregate, volatile, 0.7, discussion_quality=0.65)
    assert quality_pump["pump_risk_score"] < 0.45

    meme_aggregate = TickerAggregate(ticker="PUMP", mention_count=4)
    meme_aggregate.post_types.extend(["Meme", "Meme", "YOLO"])
    meme_aggregate.hype_count = 6
    micro = MarketData(valid=True, latest_price=1.2, avg_volume=80_000, market_cap=40_000_000)
    junk_pump = pump_risk_details(meme_aggregate, micro, 0.2, discussion_quality=0.2)
    assert junk_pump["pump_risk_score"] >= 0.55


def test_momentum_recommendation_labels():
    assert (
        recommendation_type(70, 0.25, 2.2, "News", 0.65, 0.5, discussion_quality=0.55)
        == "Volatile momentum setup"
    )
    assert (
        recommendation_type(65, 0.2, 2.8, "DD", 0.5, 0.4, discussion_quality=0.5)
        == "Strong retail acceleration"
    )
    assert recommendation_type(50, 0.75, 1.0, "Meme", 0.2, 0.1, discussion_quality=0.2) == "Low-quality pump"
