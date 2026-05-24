from scanner.scoring import recommendation_type, signal_confidence_label, signal_confidence_score


def test_recommendation_type_risk_and_noise_buckets():
    assert recommendation_type(50, 0.7, 3.0, "Meme", 0.2, 0.2) == "High-risk pump"
    assert recommendation_type(20, 0.2, 0.5, "Question", 0.1, 0.0) == "Avoid / too noisy"
    assert recommendation_type(30, 0.5, 1.0, "Other", 0.2, 0.2) == "Avoid / too noisy"


def test_recommendation_type_new_strategy_labels():
    assert (
        recommendation_type(
            70,
            0.2,
            1.2,
            "DD",
            0.7,
            0.5,
            discussion_quality=0.65,
            analyst_target=0.67,
        )
        == "Analyst upside watch"
    )
    assert (
        recommendation_type(
            70,
            0.2,
            1.2,
            "Earnings",
            0.6,
            0.2,
            catalyst_confidence=0.7,
        )
        == "Earnings momentum"
    )
    assert (
        recommendation_type(
            70,
            0.4,
            2.5,
            "News",
            0.5,
            0.4,
            acceleration_score=0.8,
            has_ai=True,
        )
        == "AI sympathy trade"
    )
    assert recommendation_type(70, 0.55, 3.0, "Meme", 0.4, 0.5) == "Meme squeeze"
    assert (
        recommendation_type(
            55,
            0.2,
            1.5,
            "News",
            0.4,
            0.1,
            bearish_score=0.5,
            avg_sentiment=-0.3,
        )
        == "Panic selloff"
    )
    assert (
        recommendation_type(
            60,
            0.2,
            1.0,
            "DD",
            0.5,
            0.3,
            discussion_quality=0.7,
            hype_count=1,
        )
        == "Institutional-style accumulation"
    )
    assert recommendation_type(70, 0.2, 2.0, "DD", 0.7, 0.5) == "Retail breakout"
    assert (
        recommendation_type(
            45,
            0.3,
            1.0,
            "DD",
            0.4,
            0.1,
            avg_sentiment=-0.2,
            discussion_quality=0.45,
        )
        == "Contrarian watchlist"
    )
    assert recommendation_type(45, 0.2, 1.2, "Other", 0.2, 0.2) == "Watchlist"


def test_signal_confidence_score_and_label():
    score = signal_confidence_score(
        subreddit_spread=0.75,
        discussion_quality=0.7,
        analyst_target=0.67,
        market_confirmation=0.8,
        pump_risk=0.2,
        unique_users=0.6,
        catalyst_confidence=0.7,
    )
    assert 0.0 <= score <= 1.0
    assert signal_confidence_label(score) in {"LOW", "MEDIUM", "HIGH"}
    assert signal_confidence_label(0.7) == "HIGH"
    assert signal_confidence_label(0.5) == "MEDIUM"
    assert signal_confidence_label(0.2) == "LOW"
