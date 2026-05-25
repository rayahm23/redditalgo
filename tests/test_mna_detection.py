"""Tests for trading-buy vs corporate M&A narrative detection."""

from scanner.narrative_extraction import (
    analyze_corporate_mna,
    detect_ma_directionality,
    detect_trading_buy_intent,
    extract_ticker_narrative,
)


def _narrative(text: str, ticker: str = "SOFI"):
    return extract_ticker_narrative(
        ticker,
        [{"title": text, "selftext": "", "comments_excerpt": "", "subreddit": "stocks"}],
        unique_subreddits=1,
    )


def test_trading_buy_does_not_trigger_mna():
    cases = [
        "I am buying SOFI tomorrow",
        "Should I buy AMD or NVDA?",
        "Bought calls on SOFI",
        "Buy the dip on SOFI",
        "SOFI is a buy",
        "I'm buying AMD shares today",
        "buy NVDA instead of SOFI",
    ]
    for text in cases:
        ticker = "SOFI" if "SOFI" in text else ("AMD" if "AMD" in text else "NVDA")
        assert detect_ma_directionality(text, ticker) == "none", text
        assert not analyze_corporate_mna(text, ticker).get("corporate_mna_intent"), text


def test_trading_buy_intent_detected():
    assert detect_trading_buy_intent("I am buying SOFI tomorrow", "SOFI")
    narrative = _narrative("Loading up on SOFI, bought calls yesterday")
    assert narrative["trading_buy_mentions_count"] >= 1
    assert "bullish trading interest" in narrative.get("bullish_themes", [])
    assert not narrative.get("mna_detected") or not narrative.get("corporate_mna_mentions_count")


def test_corporate_acquirer_detection():
    text = "SOFI is acquiring a fintech startup in an all-stock deal"
    assert detect_ma_directionality(text, "SOFI") == "acquirer"
    analysis = analyze_corporate_mna(text, "SOFI")
    assert analysis["corporate_mna_intent"]
    assert analysis["mna_direction"] == "acquirer"


def test_corporate_acquirer_amd():
    text = "AMD announced acquisition of a chip startup"
    assert detect_ma_directionality(text, "AMD") in {"acquirer", "confirmed_acquirer"}


def test_corporate_target_detection():
    for text in (
        "SOFI could be acquired by a major bank",
        "SOFI is a buyout target according to rumors",
        "Someone should acquire SOFI at a premium",
    ):
        assert detect_ma_directionality(text, "SOFI") == "target"


def test_merger_detection():
    text = "SOFI merging with another neobank in a merger between SOFI and X"
    assert detect_ma_directionality(text, "SOFI") == "merger_partner"


def test_mna_negation_not_bullish_claim():
    narrative = _narrative("No buyout is happening for SOFI, acquisition rumor was denied")
    ma_claims = [c for c in narrative.get("claims", []) if c.get("claim_type") == "M&A / corporate"]
    assert not ma_claims or narrative.get("mna_status") == "denied_or_negated"


def test_vague_mna_without_ticker_returns_none():
    text = "Lots of M&A chatter and acquisition rumors in fintech today"
    assert detect_ma_directionality(text, "SOFI") == "none"


def test_buy_word_alone_with_ticker_not_mna():
    assert detect_ma_directionality("Everyone says buy SOFI now", "SOFI") == "none"
