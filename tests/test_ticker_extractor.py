from scanner.ticker_extractor import extract_tickers_from_post, extract_tickers_from_text


def test_extracts_cashtags_and_plain_uppercase_tickers():
    text = "I like $tsla and NVDA here. TSLA still has momentum."

    assert extract_tickers_from_text(text) == ["TSLA", "NVDA", "TSLA"]


def test_filters_common_false_positives():
    text = "THE CEO said CPI and GDP matter but AMD and $msft are moving. LOL"

    assert extract_tickers_from_text(text) == ["MSFT", "AMD"]


def test_extracts_from_post_comments():
    mentions = extract_tickers_from_post(
        "Watching GME",
        "Body mentions $amc",
        ["NVDA calls", "not a ticker: YOLO"],
    )

    assert mentions == ["GME", "AMC", "NVDA"]


def test_does_not_double_count_uppercase_cashtags():
    text = "$TSLA is stronger than TSLA today"

    assert extract_tickers_from_text(text) == ["TSLA", "TSLA"]


def test_filters_trading_jargon_false_positives():
    text = "CALL PUT ITM OTM ATM RH FED EV EPS PE IV but TSLA and $nvda remain"

    assert extract_tickers_from_text(text) == ["NVDA", "TSLA"]
