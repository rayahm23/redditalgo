from scanner.market_data import MarketData
from scanner.scoring import TickerAggregate, rank_tickers_with_exclusions


def test_rank_tickers_with_exclusions_splits_penny():
    aggregates = {
        "GOOD": TickerAggregate(ticker="GOOD"),
        "BAD": TickerAggregate(ticker="BAD"),
    }
    aggregates["GOOD"].mention_count = 5
    aggregates["GOOD"].post_ids = {"p1", "p2", "p3"}
    aggregates["GOOD"].post_types = ["News", "DD"]
    aggregates["GOOD"].sentiment_scores = [0.3, 0.4]
    aggregates["GOOD"].bullish_scores = [0.6]
    aggregates["GOOD"].bearish_scores = [0.2]
    aggregates["GOOD"].post_type_weights = [0.8, 0.9]
    aggregates["GOOD"].sources = [
        {"subreddit": "stocks", "title": "GOOD stock", "selftext": "solid", "score": 50}
    ]

    aggregates["BAD"].mention_count = 1
    aggregates["BAD"].post_ids = {"p1"}
    aggregates["BAD"].low_quality_mentions = 1
    aggregates["BAD"].post_types = ["Meme"]
    aggregates["BAD"].sentiment_scores = [0.1]
    aggregates["BAD"].sources = [
        {"subreddit": "wallstreetbets", "title": "BAD", "selftext": "", "score": 1}
    ]

    market = {
        "GOOD": MarketData(valid=True, latest_price=25.0, avg_volume=2_000_000, market_cap=5_000_000_000),
        "BAD": MarketData(valid=True, latest_price=1.0, avg_volume=50_000, market_cap=10_000_000),
    }
    ranked, excluded = rank_tickers_with_exclusions(aggregates, market, limit=10)
    ranked_tickers = {row["ticker"] for row in ranked}
    excluded_tickers = {row["ticker"] for row in excluded}
    assert "GOOD" in ranked_tickers
    assert "BAD" in excluded_tickers
    assert any(row.get("exclusion_reason") for row in excluded)
