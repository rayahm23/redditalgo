"""Alert generation for ranked scanner signals."""

from __future__ import annotations

from typing import Any

ALERT_LEVELS = ("NONE", "INFO", "IMPORTANT", "HIGH")


def _level_from_alerts(alerts: list[str]) -> str:
    if not alerts:
        return "NONE"
    high_markers = ("New top-10 signal", "Attention acceleration above 3x")
    important_markers = (
        "Under-$15 momentum candidate",
        "Analyst upside above 20%",
        "Market confirmation improving",
    )
    if any(alert in high_markers for alert in alerts):
        return "HIGH"
    if any(any(marker in alert for marker in important_markers) for alert in alerts):
        return "IMPORTANT"
    return "INFO"


def _was_in_top10(ticker: str, history_snapshots: list[tuple[str, list[dict[str, Any]]]] | None) -> bool:
    if not history_snapshots:
        return False
    symbol = ticker.upper()
    for _day, rows in history_snapshots[:-1]:
        for row in rows:
            if str(row.get("ticker") or "").upper() == symbol:
                try:
                    if int(row.get("rank") or 99) <= 10:
                        return True
                except (TypeError, ValueError):
                    continue
    return False


def _prior_row(ticker: str, history_snapshots: list[tuple[str, list[dict[str, Any]]]] | None) -> dict[str, Any] | None:
    if not history_snapshots or len(history_snapshots) < 2:
        return None
    symbol = ticker.upper()
    _day, rows = history_snapshots[-2]
    return next((row for row in rows if str(row.get("ticker") or "").upper() == symbol), None)


def generate_alerts(
    row: dict[str, Any],
    *,
    history_snapshots: list[tuple[str, list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Build alert strings and overall alert level for a ranked ticker."""

    alerts: list[str] = []
    ticker = str(row.get("ticker") or "").upper()
    rank = int(row.get("rank") or 99)
    acceleration = float(row.get("attention_acceleration") or 0)
    pump = float(row.get("pump_risk_score") or 1)
    market = float(row.get("market_confirmation_score") or 0)
    upside = row.get("analyst_target_upside_pct")
    price = row.get("latest_price")
    consensus = str(row.get("consensus_label") or "")
    disagreement = float(row.get("disagreement_score") or 0)
    prior = _prior_row(ticker, history_snapshots)

    if rank <= 10 and not _was_in_top10(ticker, history_snapshots):
        alerts.append("New top-10 signal")
    if acceleration >= 3.0:
        alerts.append("Attention acceleration above 3x")
    if upside is not None and float(upside) >= 0.20 and pump < 0.35:
        alerts.append("Analyst upside above 20%")
    if price is not None and float(price) < 15 and rank <= 10:
        alerts.append("Under-$15 momentum candidate")
    if prior is not None:
        prior_market = float(prior.get("market_confirmation_score") or 0)
        if market >= prior_market + 0.15 and market >= 0.45:
            alerts.append("Market confirmation improving")
    if consensus in {"Leaning bullish", "Strong bullish consensus"} and disagreement <= 0.35:
        if prior is not None and float(prior.get("disagreement_score") or 1) > disagreement + 0.12:
            alerts.append("Bullish consensus strengthening")
    catalyst = str(row.get("catalyst_type") or "")
    if catalyst in {"Earnings", "FDA / biotech", "AI / infrastructure"} and float(
        row.get("catalyst_confidence_score") or 0
    ) >= 0.65:
        alerts.append("New strong catalyst signal")

    return {
        "alerts": alerts,
        "alert_level": _level_from_alerts(alerts),
    }
