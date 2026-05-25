from scanner.narrative_extraction import (
    CUSTOM_STOPWORDS,
    FALLBACK_NARRATIVE,
    build_narrative_summary,
    extract_finance_phrases,
    extract_ticker_narrative,
)


def test_stopwords_filtered_from_phrase_extraction():
    text = (
        "this stock have what also would could should really think going "
        "still even just much very make made many some more well good great "
        "free cash flow margin expansion earnings guidance ai demand data center growth"
    )
    phrases = extract_finance_phrases(text)
    for stop in ("have", "this", "what", "also"):
        assert stop not in [part.lower() for phrase in phrases for part in phrase.split()]
    assert any("cash flow" in phrase.lower() or "margin" in phrase.lower() for phrase in phrases)


def test_finance_phrases_prioritized_over_generic_tokens():
    text = (
        "Strong free cash flow and margin expansion after earnings guidance. "
        "AI demand and data center growth are driving revenue growth."
    )
    phrases = extract_finance_phrases(text)
    joined = " ".join(phrases).lower()
    assert "free cash flow" in joined or "margin" in joined
    assert "cash flow" in joined or "earnings" in joined
    assert "have" not in phrases
    assert "this" not in phrases


def test_phrase_clustering_merges_ai_variants():
    text = (
        "Enterprise AI demand is huge. AI datacenter buildout and data center growth "
        "are the main thesis alongside AI growth commentary."
    )
    phrases = extract_finance_phrases(text)
    assert any("AI" in phrase or "datacenter" in phrase.lower() for phrase in phrases)


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
    keywords = narrative["narrative_keywords"]
    assert keywords
    assert "have" not in keywords
    assert "this" not in keywords


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


def test_custom_stopwords_include_requested_terms():
    for word in ("have", "lol", "bro", "market", "stock"):
        assert word in CUSTOM_STOPWORDS
