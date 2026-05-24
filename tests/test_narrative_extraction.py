from scanner.narrative_extraction import (
    FALLBACK_NARRATIVE,
    build_narrative_summary,
    extract_ticker_narrative,
)


def test_narrative_detects_bullish_and_bearish_themes():
    sources = [
        {
            "title": "AMD AI datacenter demand accelerating after earnings beat",
            "selftext": "Guidance raise and strong revenue growth discussed.",
            "comments_excerpt": "Still worried about NVDA competition and valuation concerns.",
            "subreddit": "stocks",
        },
        {
            "title": "AMD enterprise GPU adoption",
            "selftext": "Analyst upgrade and technical breakout mentioned.",
            "comments_excerpt": "",
            "subreddit": "investing",
        },
    ]
    narrative = extract_ticker_narrative("AMD", sources, post_types=["Earnings", "News"], unique_subreddits=2)

    assert narrative["narrative_sources_count"] == 2
    assert "AI datacenter demand" in narrative["bullish_themes"]
    assert narrative["bearish_themes"]
    assert narrative["narrative_confidence"] in {"MEDIUM", "HIGH"}
    assert narrative["narrative_confidence_score"] >= 0.4
    assert "AMD" in narrative["primary_narrative"]


def test_narrative_fallback_when_data_is_sparse():
    narrative = extract_ticker_narrative("ZZZ", [], post_types=["Meme"], unique_subreddits=0)
    assert narrative["primary_narrative"] == FALLBACK_NARRATIVE
    assert narrative["narrative_confidence"] == "LOW"


def test_build_narrative_summary_uses_themes():
    narrative = {
        "primary_narrative": "Discussion focused on AMD's AI datacenter demand.",
        "bullish_themes": ["AI datacenter demand", "earnings optimism"],
        "bearish_themes": ["valuation concerns"],
    }
    text = build_narrative_summary(
        "AMD",
        narrative,
        attention_phrase="accelerated",
        quality_phrase="with substantive discussion",
        market_phrase="Momentum is confirming.",
    )
    assert "AMD discussion accelerated" in text
    assert "AI datacenter demand" in text
    assert "valuation concerns" in text
