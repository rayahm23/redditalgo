from scanner.market_data import MarketData, analyst_target_upside


def test_analyst_target_upside_positive_and_negative():
    assert analyst_target_upside(100, 118) == 0.18
    assert analyst_target_upside(100, 94) == -0.06
    assert analyst_target_upside(None, 100) is None


def test_market_data_includes_analyst_fields():
    data = MarketData(
        valid=True,
        latest_price=200.0,
        analyst_target_mean=240.0,
        analyst_target_upside_pct=0.2,
    )
    payload = data.to_dict()
    assert payload["analyst_target_mean"] == 240.0
    assert payload["analyst_target_upside_pct"] == 0.2
