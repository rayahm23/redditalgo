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
                "unique_posts": 12,
                "avg_sentiment": 0.61,
                "total_upvotes": 5200,
                "comment_volume": 840,
                "latest_price": 214.52,
                "market_cap": 650000000000,
                "avg_volume": 98000000,
                "risk_flag": "medium",
                "summary": "High Reddit attention with positive sentiment.",
                "top_sources": [
                    {
                        "subreddit": "wallstreetbets",
                        "title": "Example post title",
                        "permalink": "https://reddit.com/r/wallstreetbets/example",
                    }
                ],
                "generated_at": "2026-05-24T20:00:00+00:00",
            }
        ]
    )

    assert "TSLA" in html
    assert "87.4" in html
    assert "42</b> mentions" in html
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
