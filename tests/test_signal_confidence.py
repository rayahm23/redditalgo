from scanner.market_data import MarketData
from scanner.scoring import (
    TickerAggregate,
    aggregate_has_ai_catalyst,
    aggregate_posts,
    analyst_target_score,
    analyst_target_score_from_text,
    catalyst_confidence_score,
    discussion_quality_score,
    rank_tickers,
    signal_confidence_label,
    signal_confidence_score,
    unique_users_score,
)

REFERENCE_TIME = "2026-05-24T12:00:00+00:00"
TODAY = 1779624000


def test_analyst_target_score_from_text_detects_upside_language():
    assert analyst_target_score_from_text("Analyst upgrade with new price target of $250") >= 0.33
    assert analyst_target_score_from_text("Just a meme stock rocket") == 0.0


def test_aggregate_posts_tracks_authors_and_analyst_scores():
    posts = [
        {
            "id": "a",
            "author": "user_a",
            "subreddit": "stocks",
            "title": "MSFT analyst upgrade and price target raised",
            "selftext": "",
            "score": 120,
            "num_comments": 30,
            "created_utc": TODAY,
            "permalink": "https://reddit.com/a",
            "top_comments": [],
        },
        {
            "id": "b",
            "author": "user_b",
            "subreddit": "investing",
            "title": "MSFT earnings guidance looks strong",
            "selftext": "",
            "score": 80,
            "num_comments": 15,
            "created_utc": TODAY,
            "permalink": "https://reddit.com/b",
            "top_comments": [],
        },
    ]

    aggregates = aggregate_posts(posts, reference_time=REFERENCE_TIME)
    aggregate = aggregates["MSFT"]

    assert aggregate.unique_users == 2
    assert analyst_target_score(aggregate) > 0
    assert discussion_quality_score(aggregate) > 0
    assert catalyst_confidence_score(aggregate) > 0
    assert unique_users_score(aggregate) > 0


def test_aggregate_has_ai_catalyst_from_source_titles():
    aggregate = TickerAggregate(ticker="NVDA")
    aggregate.sources.append({"title": "Generative AI demand is accelerating for NVDA"})
    assert aggregate_has_ai_catalyst(aggregate) is True


def test_rank_tickers_includes_confidence_fields():
    aggregate = TickerAggregate(
        ticker="TSLA",
        mention_count=3,
        weighted_mention_count=3.0,
        weighted_unique_posts=1.0,
        total_upvotes=100,
        comment_volume=10,
    )
    aggregate.post_ids.add("post-1")
    aggregate.authors.add("trader_1")
    aggregate.sentiment_scores.append(0.2)
    aggregate.post_types.append("DD")
    aggregate.post_type_weights.append(1.5)
    aggregate.analyst_target_scores.append(0.33)
    aggregate.sources.append(
        {
            "subreddit": "stocks",
            "title": "TSLA price target raised by analyst",
            "permalink": "https://reddit.com/x",
            "score": 100,
            "created_utc": TODAY,
            "recency_weight": 1.0,
            "post_type": "DD",
        }
    )

    results = rank_tickers(
        {"TSLA": aggregate},
        {
            "TSLA": MarketData(
                valid=True,
                latest_price=200,
                avg_volume=10_000_000,
                market_cap=700_000_000_000,
                one_day_return=0.02,
                five_day_return=0.04,
                relative_volume=1.2,
            )
        },
        generated_at="2026-05-24T00:00:00+00:00",
    )

    row = results[0]
    assert "signal_confidence_score" in row
    assert row["signal_confidence_label"] in {"LOW", "MEDIUM", "HIGH"}
    assert "recommendation_type" in row
    assert 0.0 <= row["signal_confidence_score"] <= 1.0
    assert row["unique_users"] == 1
    assert len(row["historical_trends"]["mentions_7d"]) == 7
    assert row["historical_trends"]["mentions_7d"][-1] == 3
    assert row["sparklines"]["length"] == 7
