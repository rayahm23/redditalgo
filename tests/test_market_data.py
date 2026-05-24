from scanner.market_data import analyst_target_signal


def test_analyst_target_signal_defaults_to_neutral_when_missing():
    signal = analyst_target_signal(latest_price=100, target_mean_price=None)

    assert signal["analyst_target_upside_pct"] is None
    assert signal["analyst_target_score"] == 0.50
    assert signal["analyst_target_label"] == "missing target data"


def test_analyst_target_signal_scores_upside_buckets():
    assert analyst_target_signal(100, 70)["analyst_target_label"] == "major downside"
    assert analyst_target_signal(100, 90)["analyst_target_score"] == 0.25
    assert analyst_target_signal(100, 103)["analyst_target_score"] == 0.50
    assert analyst_target_signal(100, 115)["analyst_target_score"] == 0.70
    assert analyst_target_signal(100, 140)["analyst_target_score"] == 0.90
    assert analyst_target_signal(100, 200)["analyst_target_score"] == 0.75
