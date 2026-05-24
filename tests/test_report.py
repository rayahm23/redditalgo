from pathlib import Path

from scanner.report import render_results_html, write_html_reports


def test_render_results_html_includes_ticker_metrics_and_disclaimer():
    html = render_results_html(
        [
            {
                "rank": 1,
                "ticker": "TSLA",
                "final_score": 87.4,
                "recommendation_type": "Retail breakout",
                "signal_confidence_label": "HIGH",
                "analyst_target_score": 0.67,
                "catalyst_type": "DD",
                "historical_trends": {
                    "mentions_7d": [1, 2, 3, 4, 5, 6, 7],
                    "sentiment_7d": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
                    "score_7d": [40, 45, 50, 55, 60, 65, 70],
                    "analyst_target_upside_7d": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.67],
                },
                "sparklines": {
                    "mentions": [1, 2, 3, 4, 5, 6, 7],
                    "sentiment": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
                    "score": [40, 45, 50, 55, 60, 65, 70],
                    "analyst_target_upside": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.67],
                    "length": 7,
                },
                "risk_flag": "medium",
                "risk_explanation": "No major pump/noise signals detected.",
                "mention_count": 42,
                "unique_posts": 12,
                "unique_subreddits": 2,
                "seven_day_avg_mentions": 10,
                "attention_acceleration": 4.2,
                "avg_sentiment": 0.61,
                "net_conviction_score": 0.75,
                "market_confirmation_score": 0.8,
                "pump_risk_score": 0.1,
                "latest_price": 214.52,
                "market_cap": 650000000000,
                "avg_volume": 98000000,
                "one_day_return": 0.02,
                "five_day_return": 0.05,
                "relative_volume": 1.8,
                "dominant_post_type": "DD",
                "risk_reasons": ["Valid market data is available, but the ticker does not meet all low-risk liquidity and market-cap thresholds."],
                "score_breakdown": {
                    "attention_acceleration_score": 1.0,
                    "engagement_quality_score": 0.8,
                    "sentiment_score": 0.805,
                    "net_conviction_score": 0.75,
                    "market_confirmation_score": 0.8,
                    "subreddit_spread_score": 0.5,
                    "pump_risk_penalty": 0.02,
                    "raw_score_0_to_1": 0.75,
                    "final_score": 75.0,
                    "formula": "0.25*attention_acceleration + 0.20*engagement_quality + 0.15*sentiment + 0.15*net_conviction + 0.15*market_confirmation + 0.10*subreddit_spread - pump_risk_penalty",
                },
                "summary": "High Reddit attention with positive sentiment.",
                "top_sources": [
                    {
                        "subreddit": "wallstreetbets",
                        "title": "Example post title",
                        "permalink": "https://reddit.com/r/wallstreetbets/example",
                        "recency_weight": 1.0,
                        "post_type": "DD",
                    }
                ],
                "generated_at": "2026-05-24T20:00:00+00:00",
            }
        ]
    )

    assert "TSLA" in html
    assert "87.4" in html
    assert "42</b> mentions" in html
    assert "4.20x</b> acceleration" in html
    assert "Score breakdown" in html
    assert "Risk explanation" in html
    assert "Formula:" in html
    assert "Retail breakout" in html
    assert "HIGH confidence" in html
    assert "Analyst upside" in html
    assert "DD catalyst" in html
    assert 'class="sparkline"' in html
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
