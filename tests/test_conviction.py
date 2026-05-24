from scanner.conviction import conviction_scores


def test_conviction_scores_detect_bullish_and_bearish_phrases():
    bullish = conviction_scores("Buying calls", "loaded and holding shares into earnings")
    bearish = conviction_scores("Buying puts", "overvalued with dilution downside")

    assert bullish["bullish_conviction_score"] > bullish["bearish_conviction_score"]
    assert bearish["bearish_conviction_score"] > bearish["bullish_conviction_score"]
    assert 0 <= bullish["net_conviction_score"] <= 1
