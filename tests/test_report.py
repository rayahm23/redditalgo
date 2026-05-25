from pathlib import Path

from scanner.report import render_results_html, write_html_reports


def _sample_row() -> dict:
    return {
        "rank": 1,
        "ticker": "AMD",
        "final_score": 68.7,
                "recommendation_type": "Volatile momentum setup",
        "signal_confidence_label": "HIGH",
        "catalyst_type": "Earnings",
                "risk_flag": "medium",
        "analyst_target_mean": 550.0,
        "analyst_target_upside_pct": 0.18,
        "latest_price": 467.51,
        "attention_acceleration": 4.2,
        "five_day_return": 0.1024,
        "unique_subreddits": 3,
        "mention_count": 9,
        "unique_posts": 3,
        "avg_sentiment": 0.39,
        "net_conviction_score": 0.67,
        "market_confirmation_score": 0.5,
        "pump_risk_score": 0.19,
        "relative_volume": 0.9,
        "signal_summaries": {
            "retail_attention": "Strong",
            "discussion_quality": "Strong",
            "market_confirmation": "Moderate",
            "speculation_risk": "Weak",
            "analyst_outlook": "Strong",
        },
        "historical_trends": {
            "mentions_7d": [1, 2, 3, 4, 5, 6, 9],
            "score_7d": [40, 45, 50, 55, 60, 65, 68.7],
        },
        "sparklines": {
            "mentions": [1, 2, 3, 4, 5, 6, 9],
            "score": [40, 45, 50, 55, 60, 65, 68.7],
        },
        "score_breakdown": {
            "attention_acceleration_score": 1.0,
            "engagement_quality_score": 0.8,
            "sentiment_score": 0.7,
            "net_conviction_score": 0.67,
            "market_confirmation_score": 0.5,
            "subreddit_spread_score": 0.75,
            "pump_risk_penalty": 0.04,
            "raw_score_0_to_1": 0.69,
            "final_score": 68.7,
            "formula": "weighted model",
        },
        "summary": (
            "AMD discussion accelerated as users focused on earnings and guidance, "
            "with relatively substantive thread quality."
        ),
        "risk_explanation": "No major pump/noise signals detected.",
        "risk_reasons": ["Liquid large-cap profile."],
        "top_sources": [
            {
                "subreddit": "stocks",
                "title": "AMD earnings and AI demand",
                "permalink": "https://reddit.com/r/stocks/example",
                "post_type": "Earnings",
            }
        ],
        "primary_narrative": "Users linked AMD to AI accelerator demand and enterprise GPU adoption.",
        "primary_claim": {
            "claim_text": "Users linked AMD to AI accelerator demand and enterprise GPU adoption.",
            "short_label": "AI GPU / datacenter demand",
        },
        "bullish_themes": ["AI GPU / datacenter demand", "earnings beat / guidance raise"],
        "bearish_themes": ["valuation concern after rally"],
        "bullish_claims": [{"short_label": "AI GPU / datacenter demand"}],
        "evidence_snippets": ["AMD AI datacenter GPU demand accelerating"],
        "narrative_keywords": ["earnings", "datacenter"],
        "generated_at": "2026-05-24T20:00:00+00:00",
    }


def test_render_results_html_polished_dashboard_layout():
    html = render_results_html([_sample_row()])

    assert "General Signals" in html
    assert "Small Stocks Under $15" in html
    assert "Discussion Summary" in html
    assert "Primary Claim" in html
    assert "Bullish Claims" in html
    assert "Narrative keywords" not in html
    assert "AMD" in html
    assert "68" in html
    assert "Volatile momentum setup" in html
    assert "High Confidence" in html
    assert "Earnings Catalyst" in html
    assert "Investable" in html
    assert "$550" in html and "+18%" in html
    assert "Analyst mention" not in html
    assert "Retail Attention" in html
    assert "Speculation Risk" in html
    assert 'class="chip' not in html
    assert "Score breakdown" in html
    assert "Algorithm details" in html
    assert 'details class="nested-details"' in html or "Algorithm details" in html
    assert "Formula:" in html
    assert 'class="sparkline"' in html
    assert "Sentiment" not in html or "Historical trends" in html
    assert "Not financial advice" in html
    assert "0.19" not in html
    assert "Catalyst details" in html


def test_write_html_reports_creates_current_and_history_files(tmp_path: Path):
    output_path = tmp_path / "data" / "daily_results.json"
    history_dir = tmp_path / "data" / "history"
    output_path.parent.mkdir(parents=True)
    history_dir.mkdir(parents=True)

    write_html_reports([], output_path, history_dir, "2026-05-24")

    assert (tmp_path / "data" / "daily_results.html").exists()
    assert (tmp_path / "data" / "history" / "2026-05-24.html").exists()
