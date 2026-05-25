from scanner.narrative_extraction import (
    CUSTOM_STOPWORDS,
    FALLBACK_NARRATIVE,
    build_narrative_summary,
    detect_ma_directionality,
    extract_finance_phrases,
    extract_ticker_narrative,
)


def test_stopwords_filtered_from_phrase_extraction():
    text = (
        "this stock have what also would could should really think going "
        "free cash flow margin expansion earnings guidance ai demand data center growth"
    )
    phrases = extract_finance_phrases(text)
    for stop in ("have", "this", "what", "also"):
        assert stop not in [part.lower() for phrase in phrases for part in phrase.split()]
    assert any("cash flow" in phrase.lower() or "margin" in phrase.lower() for phrase in phrases)


def test_ma_directionality_acquirer():
    text = "SOFI is acquiring a smaller fintech and the deal to buy could close soon."
    assert detect_ma_directionality(text, "SOFI") == "acquirer"


def test_ma_directionality_target():
    text = "Rumors that SOFI is a buyout target and could be bought by a larger bank."
    assert detect_ma_directionality(text, "SOFI") == "target"


def test_ma_directionality_merger():
    text = "SOFI merging with another neobank in an all-stock merger with regulatory review."
    assert detect_ma_directionality(text, "SOFI") == "merger_partner"


def test_ma_directionality_unclear_without_subject():
    text = "Lots of M&A chatter and acquisition rumors in fintech today."
    assert detect_ma_directionality(text, "SOFI") in {"vague", "unclear", "none"}


def test_amd_gets_specific_ai_gpu_claim_not_generic_datacenter_only():
    sources = [
        {
            "title": "AMD AI datacenter GPU demand accelerating after earnings beat",
            "selftext": "Enterprise GPU adoption and accelerator demand vs NVDA.",
            "comments_excerpt": "Still worried about valuation concerns.",
            "subreddit": "stocks",
        },
        {
            "title": "AMD MI300 ramp",
            "selftext": "Data center GPU shipments discussed.",
            "comments_excerpt": "",
            "subreddit": "investing",
        },
    ]
    narrative = extract_ticker_narrative("AMD", sources, post_types=["Earnings"], unique_subreddits=2)
    primary = narrative["primary_claim"]
    assert primary is not None
    assert "datacenter" in primary["claim_text"].lower() or "gpu" in primary["claim_text"].lower()
    assert "AI datacenter demand" not in narrative["bullish_themes"]
    assert any("gpu" in label.lower() or "datacenter" in label.lower() for label in narrative["bullish_themes"])


def test_sofi_gets_ai_lending_not_datacenter_play():
    sources = [
        {
            "title": "SOFI AI lending automation could improve loan approvals",
            "selftext": "Fintech efficiency and underwriting AI discussed.",
            "comments_excerpt": "Loan growth and member growth look strong.",
            "subreddit": "stocks",
        },
        {
            "title": "SOFI as a growth fintech",
            "selftext": "Not a datacenter name — digital banking focus.",
            "comments_excerpt": "",
            "subreddit": "investing",
        },
    ]
    narrative = extract_ticker_narrative("SOFI", sources, unique_subreddits=2)
    labels = " ".join(narrative["bullish_themes"]).lower()
    assert "lending" in labels or "loan" in labels or "fintech" in narrative["primary_narrative"].lower()
    assert "AI GPU / datacenter demand" not in narrative["bullish_themes"]


def test_ma_acquirer_claim_text():
    sources = [
        {
            "title": "SOFI plans to acquire a payments startup",
            "selftext": "Deal to buy could expand product stack.",
            "comments_excerpt": "",
            "subreddit": "stocks",
        },
    ]
    narrative = extract_ticker_narrative("SOFI", sources, unique_subreddits=1)
    ma_claims = [c for c in narrative["claims"] if c.get("claim_type") == "M&A / corporate"]
    assert ma_claims
    assert "acquire" in ma_claims[0]["claim_text"].lower()
    assert narrative["ma_direction"] is not None


def test_ma_unclear_claim_when_direction_unknown():
    sources = [
        {
            "title": "SOFI and M&A rumors everywhere",
            "selftext": "Acquisition takeover buyout chatter but no clear buyer or target.",
            "comments_excerpt": "",
            "subreddit": "wallstreetbets",
        },
    ]
    narrative = extract_ticker_narrative("SOFI", sources, unique_subreddits=1)
    ma_claims = [c for c in narrative["claims"] if "unclear" in c.get("directionality", "")]
    assert ma_claims
    assert "unclear" in ma_claims[0]["claim_text"].lower() or "did not clearly" in ma_claims[0]["claim_text"].lower()


def test_vague_ai_fallback():
    sources = [
        {
            "title": "SOFI is an AI play now",
            "selftext": "AI AI AI with no detail.",
            "comments_excerpt": "",
            "subreddit": "stocks",
        },
    ]
    narrative = extract_ticker_narrative("SOFI", sources, unique_subreddits=1)
    assert (
        "unclear" in narrative["primary_narrative"].lower()
        or "impact was unclear" in narrative["primary_narrative"].lower()
        or "AI" in narrative["primary_narrative"]
    )


def test_claim_confidence_scoring():
    sources = [
        {
            "title": f"Post {index} SOFI loan growth and AI lending automation",
            "selftext": "Multiple comments on underwriting AI.",
            "comments_excerpt": "Strong origination growth.",
            "subreddit": "stocks" if index % 2 == 0 else "investing",
        }
        for index in range(4)
    ]
    narrative = extract_ticker_narrative("SOFI", sources, unique_subreddits=2)
    assert narrative["claims"]
    top = narrative["claims"][0]
    assert top["confidence_score"] >= 0.4
    assert top["confidence_label"] in {"Medium", "High", "Low"}
    assert top["source_count"] >= 2
    assert narrative["evidence_snippets"]


def test_narrative_fallback_when_data_is_sparse():
    narrative = extract_ticker_narrative("ZZZ", [], post_types=["Meme"], unique_subreddits=0)
    assert narrative["primary_narrative"] == FALLBACK_NARRATIVE
    assert narrative["narrative_confidence"] == "LOW"


def test_build_narrative_summary_uses_claims():
    narrative = {
        "primary_narrative": "Users discussed SOFI as a fintech growth name with AI lending automation.",
        "primary_claim": {
            "claim_text": "Users discussed SOFI as a fintech growth name with AI lending automation.",
            "short_label": "AI lending automation",
        },
        "bullish_claims": [{"short_label": "AI lending automation"}],
        "bearish_claims": [{"short_label": "valuation concern after rally"}],
        "ma_direction": "unclear",
    }
    text = build_narrative_summary(
        "SOFI",
        narrative,
        attention_phrase="rose",
        quality_phrase="with substantive discussion",
        market_phrase="Momentum is confirming.",
    )
    assert "SOFI discussion rose" in text
    assert "lending" in text.lower() or "fintech" in text.lower()
    assert "valuation" in text.lower()
    assert "M&A" in text or "unclear" in text


def test_custom_stopwords_include_requested_terms():
    for word in ("have", "lol", "bro", "market", "stock"):
        assert word in CUSTOM_STOPWORDS
