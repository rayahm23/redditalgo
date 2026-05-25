from scanner.watch_reasons import build_watch_reasons


def test_watch_and_caution_reasons():
    row = {
        "attention_acceleration": 3.0,
        "pump_risk_score": 0.2,
        "market_confirmation_score": 0.65,
        "discussion_quality_score": 0.7,
        "consensus_label": "Mixed / contested",
        "disagreement_score": 0.6,
        "ma_direction": "unclear",
    }
    watch, caution = build_watch_reasons(row)
    assert watch
    assert caution
    assert "mixed" in caution.lower() or "M&A" in caution
