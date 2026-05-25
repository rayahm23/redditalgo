from scanner.alerts import generate_alerts
from scanner.filters import evaluate_hard_filter
from scanner.market_data import MarketData
from scanner.peers import apply_peer_context, peer_group_for_ticker
from scanner.scoring import TickerAggregate


def test_peer_group_mapping():
    sector, group, peers = peer_group_for_ticker("AMD")
    assert sector == "Semiconductors"
    assert group == "semiconductors"
    assert "NVDA" in peers


def test_hard_filter_excludes_sub_two_dollar():
    aggregate = TickerAggregate(ticker="JUNK")
    aggregate.post_ids = {"a", "b", "c"}
    market = MarketData(valid=True, latest_price=1.2, avg_volume=500_000, market_cap=80_000_000)
    excluded, reason = evaluate_hard_filter(
        "JUNK",
        aggregate,
        market,
        spam_metrics={"spam_cluster_score": 0.1},
        pump_risk_score=0.3,
    )
    assert excluded is True
    assert "below" in reason.lower()


def test_generate_alerts_new_top10():
    row = {
        "ticker": "AMD",
        "rank": 3,
        "attention_acceleration": 3.5,
        "pump_risk_score": 0.2,
        "analyst_target_upside_pct": 0.25,
        "latest_price": 120,
        "market_confirmation_score": 0.6,
        "consensus_label": "Leaning bullish",
        "disagreement_score": 0.2,
        "catalyst_confidence_score": 0.7,
        "catalyst_type": "Earnings",
    }
    payload = generate_alerts(row, history_snapshots=[])
    assert payload["alert_level"] in {"HIGH", "IMPORTANT", "INFO", "NONE"}
    assert payload["alerts"]


def test_apply_peer_context_summary():
    rows = [
        {"ticker": "AMD", "attention_acceleration": 4.0, "final_score": 80},
        {"ticker": "NVDA", "attention_acceleration": 2.0, "final_score": 75},
    ]
    enriched = apply_peer_context(rows)
    amd = next(row for row in enriched if row["ticker"] == "AMD")
    assert amd.get("peer_attention_rank") == 1
    assert amd.get("peer_context_summary")
