from scanner.market_data import MarketData
from scanner.scoring import (
    TickerAggregate,
    aggregate_posts,
    calculate_final_score,
    determine_risk_flag,
    rank_tickers,
    recency_weight,
    risk_details,
    score_breakdown,
)

REFERENCE_TIME = "2026-05-24T12:00:00+00:00"
TODAY = 1779624000
YESTERDAY = TODAY - 86_400
EIGHT_DAYS_AGO = TODAY - 8 * 86_400


def test_aggregate_posts_counts_mentions_and_unique_posts_with_recency_weights():
    posts = [
        {
            "id": "a",
            "subreddit": "wallstreetbets",
            "title": "TSLA TSLA breakout",
            "selftext": "I like $tsla",
            "score": 100,
            "num_comments": 20,
            "created_utc": TODAY,
            "permalink": "https://reddit.com/a",
            "top_comments": ["TSLA looks strong"],
        },
        {
            "id": "b",
            "subreddit": "stocks",
            "title": "NVDA and TSLA watchlist",
            "selftext": "",
            "score": 50,
            "num_comments": 5,
            "created_utc": YESTERDAY,
            "permalink": "https://reddit.com/b",
            "top_comments": [],
        },
        {
            "id": "old",
            "subreddit": "stocks",
            "title": "TSLA old mention should be ignored",
            "selftext": "",
            "score": 999,
            "num_comments": 999,
            "created_utc": EIGHT_DAYS_AGO,
            "permalink": "https://reddit.com/old",
            "top_comments": [],
        },
    ]

    aggregates = aggregate_posts(posts, reference_time=REFERENCE_TIME)

    assert aggregates["TSLA"].mention_count == 5
    assert aggregates["TSLA"].unique_posts == 2
    assert aggregates["TSLA"].total_upvotes == 150
    assert aggregates["TSLA"].comment_volume == 25
    assert aggregates["NVDA"].mention_count == 1
    assert aggregates["TSLA"].weighted_mention_count == 4 * 1.0 + 1 * 0.85
    assert round(aggregates["TSLA"].weighted_unique_posts, 2) == 1.85


def test_recency_weight_descends_and_filters_old_posts():
    assert recency_weight(TODAY, REFERENCE_TIME) == 1.0
    assert recency_weight(YESTERDAY, REFERENCE_TIME) == 0.85
    assert recency_weight(EIGHT_DAYS_AGO, REFERENCE_TIME) == 0.0
    assert recency_weight(None, REFERENCE_TIME) == 0.0


def test_risk_flags_and_reasons_from_market_data():
    assert determine_risk_flag(MarketData(valid=False)) == "high"
    assert "No valid market data" in risk_details(MarketData(valid=False))["risk_reasons"][0]
    high = risk_details(MarketData(valid=True, latest_price=2.5, avg_volume=5_000_000, market_cap=2_000_000_000))
    assert high["risk_flag"] == "high"
    assert high["risk_reasons"] == ["Penny stock: latest price is below $5."]
    assert determine_risk_flag(MarketData(valid=True, latest_price=50, avg_volume=3_000_000, market_cap=15_000_000_000)) == "low"
    assert determine_risk_flag(MarketData(valid=True, latest_price=20, avg_volume=800_000, market_cap=2_000_000_000)) == "medium"


def test_score_rewards_attention_and_penalizes_high_risk():
    aggregate = TickerAggregate(
        ticker="TSLA",
        mention_count=10,
        weighted_mention_count=8.5,
        weighted_unique_posts=2.7,
        total_upvotes=1_000,
        comment_volume=200,
        sentiment_scores=[0.5, 0.7],
    )
    aggregate.post_ids.update({"a", "b", "c"})

    low_risk_score = calculate_final_score(
        aggregate, MarketData(valid=True, latest_price=200, avg_volume=50_000_000, market_cap=500_000_000_000)
    )
    high_risk_score = calculate_final_score(
        aggregate, MarketData(valid=True, latest_price=2, avg_volume=100_000, market_cap=50_000_000)
    )

    assert low_risk_score > high_risk_score
    assert 0 <= low_risk_score <= 100
    breakdown = score_breakdown(
        aggregate, MarketData(valid=True, latest_price=200, avg_volume=50_000_000, market_cap=500_000_000_000)
    )
    assert "attention_acceleration" in breakdown["formula"]
    assert breakdown["attention_acceleration_score"] >= 0
    assert breakdown["engagement_quality_score"] > 0


def test_rank_tickers_excludes_invalid_market_data_and_adds_breakdowns():
    aggregate = TickerAggregate(
        ticker="TSLA",
        mention_count=3,
        weighted_mention_count=2.55,
        weighted_unique_posts=0.85,
        total_upvotes=100,
        comment_volume=10,
    )
    aggregate.post_ids.add("post-1")
    aggregate.sentiment_scores.append(0.2)
    aggregate.sources.append(
        {
            "subreddit": "stocks",
            "title": "TSLA",
            "permalink": "https://reddit.com/x",
            "score": 100,
            "created_utc": YESTERDAY,
            "recency_weight": 0.85,
        }
    )

    invalid = TickerAggregate(ticker="FAKE", mention_count=20, weighted_mention_count=20)
    invalid.post_ids.add("post-2")

    results = rank_tickers(
        {"TSLA": aggregate, "FAKE": invalid},
        {
            "TSLA": MarketData(valid=True, latest_price=200, avg_volume=10_000_000, market_cap=700_000_000_000),
            "FAKE": MarketData(valid=False),
        },
        generated_at="2026-05-24T00:00:00+00:00",
    )

    assert [row["ticker"] for row in results] == ["TSLA"]
    assert results[0]["rank"] == 1
    assert results[0]["generated_at"] == "2026-05-24T00:00:00+00:00"
    assert results[0]["weighted_mention_count"] == 2.55
    assert "score_breakdown" in results[0]
    assert "risk_reasons" in results[0]
    assert results[0]["top_sources"][0]["recency_weight"] == 0.85
