"""Watchlist reason and caution text for ranked tickers."""

from __future__ import annotations

from typing import Any


def build_watch_reasons(row: dict[str, Any]) -> tuple[str, str]:
    """Return (watch_reason, caution_reason) for dashboard display."""

    acceleration = float(row.get("attention_acceleration") or 0)
    pump = float(row.get("pump_risk_score") or 0)
    market = float(row.get("market_confirmation_score") or 0)
    discussion = float(row.get("discussion_quality_score") or 0)
    upside = row.get("analyst_target_upside_pct")
    price = row.get("latest_price")
    consensus = str(row.get("consensus_label") or "Unclear")
    ma_direction = row.get("ma_direction")

    watch_parts: list[str] = []
    if acceleration >= 2.5 and pump <= 0.4 and market >= 0.45:
        watch_parts.append("Strong Reddit acceleration, low pump risk, and positive market confirmation.")
    elif upside is not None and float(upside) >= 0.12 and discussion >= 0.55:
        watch_parts.append("Analyst targets imply upside and discussion quality is above average.")
    elif price is not None and float(price) < 15 and acceleration >= 1.5 and market >= 0.35:
        watch_parts.append("Under-$15 name with strong retail momentum and improving volume.")
    elif discussion >= 0.6 and pump <= 0.35:
        watch_parts.append("Substantive discussion quality with limited low-quality hype.")
    else:
        watch_parts.append("Score and attention metrics place it on today's watchlist.")

    caution_parts: list[str] = []
    if market < 0.4:
        caution_parts.append("Market confirmation is still only moderate.")
    if consensus == "Mixed / contested":
        caution_parts.append("Discussion is mixed and competing narratives appeared repeatedly.")
    elif consensus == "Leaning bearish" or consensus == "Strong bearish consensus":
        caution_parts.append("Bearish pushback is meaningful relative to bullish comments.")
    if float(row.get("disagreement_score") or 0) >= 0.55:
        caution_parts.append("Users disagree on direction, so conviction is not one-sided.")
    if ma_direction and "unclear" in str(ma_direction).lower():
        caution_parts.append("M&A language appeared, but directionality was unclear.")
    if pump >= 0.45:
        caution_parts.append("Speculative or spam-like language elevated pump risk.")
    spam_expl = str(row.get("spam_risk_explanation") or "")
    if "duplicate" in spam_expl.lower() or "cluster" in spam_expl.lower():
        caution_parts.append("Duplicate or coordinated copy-paste style posts were detected.")
    if not caution_parts:
        caution_parts.append("No major caution flags beyond normal retail-volatility risk.")

    return watch_parts[0], caution_parts[0]
