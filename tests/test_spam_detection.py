from scanner.scoring import TickerAggregate
from scanner.spam_detection import analyze_spam, duplicate_content_score


def test_duplicate_content_score_detects_similar_posts():
    sources = [
        {"title": "AMD to the moon rocket rocket", "selftext": "buy amd now", "comments_excerpt": ""},
        {"title": "AMD to the moon rocket rocket", "selftext": "buy amd now", "comments_excerpt": ""},
    ]
    assert duplicate_content_score(sources) >= 0.75


def test_analyze_spam_includes_explanation():
    aggregate = TickerAggregate(ticker="GME")
    aggregate.hype_count = 12
    aggregate.max_repeated_mentions = 6
    aggregate.sources = [
        {"title": "GME moon", "selftext": "rocket", "comments_excerpt": "", "author": "pumper1"},
        {"title": "GME moon again", "selftext": "rocket", "comments_excerpt": "", "author": "pumper1"},
    ]
    metrics = analyze_spam(aggregate)
    assert metrics["spam_cluster_score"] >= 0
    assert "duplicate_content_score" in metrics
    assert metrics["spam_risk_explanation"]
