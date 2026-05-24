from scanner.subreddit_weights import (
    all_configured_subreddits,
    compute_subreddit_metrics,
    corroboration_factor,
    subreddit_group,
    subreddit_weight,
)


def test_subreddit_groups_and_weights():
    assert subreddit_group("SecurityAnalysis") == "high_quality"
    assert subreddit_group("wallstreetbets") == "high_momentum"
    assert subreddit_group("GrowthStocks") == "growth_speculative"
    assert subreddit_weight("SecurityAnalysis") == 1.4
    assert subreddit_weight("Shortsqueeze") == 0.7
    assert len(all_configured_subreddits()) >= 20


def test_compute_subreddit_metrics_and_corroboration():
    sources = [
        {"subreddit": "SecurityAnalysis", "recency_weight": 1.0},
        {"subreddit": "stocks", "recency_weight": 0.9},
        {"subreddit": "Shortsqueeze", "recency_weight": 1.0},
    ]
    metrics = compute_subreddit_metrics(sources)
    assert "high_quality" in metrics["subreddit_groups_detected"]
    assert metrics["subreddit_weighted_score"] > 0.5
    assert metrics["noisy_subreddit_exposure"] > 0
    assert corroboration_factor(metrics) > 0
