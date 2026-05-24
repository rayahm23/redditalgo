from pathlib import Path

from scanner.report import render_results_html, write_html_reports


def test_render_results_html_includes_ticker_metrics_and_disclaimer():
    html = render_results_html(
        [
            {
                "rank": 1,
                "ticker": "TSLA",
                "final_score": 87.4,
                "mention_count": 42,
                "weighted_mention_count": 36.2,
                "unique_posts": 12,
                "weighted_unique_posts": 9.4,
                "avg_sentiment": 0.61,
                "total_upvotes": 5200,
                "comment_volume": 840,
                "latest_price": 214.52,
                "market_cap": 650000000000,
                "avg_volume": 98000000,
                "risk_flag": "medium",
                "risk_reasons": ["Valid market data is available, but the ticker does not meet all low-risk liquidity and market-cap thresholds."],
                "score_breakdown": {
                    "attention_score": 41.2,
                    "engagement_score": 32.1,
                    "sentiment_score": 17.7,
                    "market_validity_bonus": 8,
                    "risk_penalty": 4,
                    "raw_score_before_cap": 99.0,
                    "capped_score_before_risk": 99.0,
                    "final_score": 95.0,
                    "recency_window_days": 7,
                    "recency_weights": [1.0, 0.85, 0.7, 0.55, 0.4, 0.25, 0.1],
                    "formula": "min(100, attention + engagement + sentiment + market_validity_bonus) - risk_penalty",
                },
                "summary": "High Reddit attention with positive sentiment.",
                "top_sources": [
                    {
                        "subreddit": "wallstreetbets",
                        "title": "Example post title",
                        "permalink": "https://reddit.com/r/wallstreetbets/example",
                        "recency_weight": 1.0,
                    }
                ],
                "generated_at": "2026-05-24T20:00:00+00:00",
            }
        ]
    )

    assert "TSLA" in html
    assert "87.4" in html
    assert "42</b> raw mentions" in html
    assert "36.20</b> weighted mentions" in html
    assert "Score breakdown" in html
    assert "Risk explanation" in html
    assert "7-day recency weights" in html
    assert "medium risk" in html
    assert "Not financial advice" in html
    assert "https://reddit.com/r/wallstreetbets/example" in html


def test_write_html_reports_creates_current_and_history_files(tmp_path: Path):
    output_path = tmp_path / "data" / "daily_results.json"
    history_dir = tmp_path / "data" / "history"
    output_path.parent.mkdir(parents=True)
    history_dir.mkdir(parents=True)

    write_html_reports([], output_path, history_dir, "2026-05-24")

    assert (tmp_path / "data" / "daily_results.html").exists()
    assert (tmp_path / "data" / "history" / "2026-05-24.html").exists()
