"""Hard do-not-rank filters for low-quality or uninvestable tickers."""

from __future__ import annotations

from typing import Any

from scanner.market_data import MarketData

HARD_PRICE_FLOOR = 2.0
HARD_AVG_VOLUME_FLOOR = 75_000
HARD_MARKET_CAP_FLOOR = 25_000_000
HARD_PUMP_RISK_CEILING = 0.88
HARD_SPAM_CLUSTER_CEILING = 0.82


def is_probable_otc(ticker: str, market_data: MarketData) -> bool:
    """Heuristic OTC detection when ticker shape or market cap suggests it."""

    symbol = ticker.upper()
    if len(symbol) >= 5 and symbol.endswith("F"):
        return True
    if "." in symbol:
        return True
    if market_data.market_cap is not None and market_data.market_cap < 5_000_000:
        return True
    return False


def evaluate_hard_filter(
    ticker: str,
    aggregate: Any,
    market_data: MarketData,
    *,
    spam_metrics: dict[str, Any],
    pump_risk_score: float,
) -> tuple[bool, str]:
    """
    Return (excluded, exclusion_reason).

    Volatility alone never triggers exclusion.
    """

    if not market_data.valid:
        return True, "Invalid or missing market data."

    price = market_data.latest_price
    if price is not None and price < HARD_PRICE_FLOOR:
        return True, f"Share price below ${HARD_PRICE_FLOOR:.0f} hard floor."

    if is_probable_otc(ticker, market_data):
        return True, "Probable OTC or illiquid microcap profile."

    if market_data.avg_volume is not None and market_data.avg_volume < HARD_AVG_VOLUME_FLOOR:
        return True, "Average volume is extremely low."

    if market_data.market_cap is not None and market_data.market_cap < HARD_MARKET_CAP_FLOOR:
        return True, "Market cap is extremely small."

    if int(getattr(aggregate, "unique_posts", 0) or 0) <= 1 and int(
        getattr(aggregate, "low_quality_mentions", 0) or 0
    ) >= 1:
        return True, "Ticker appears in only one low-quality post."

    spam_cluster = float(spam_metrics.get("spam_cluster_score") or 0)
    if spam_cluster >= HARD_SPAM_CLUSTER_CEILING:
        return True, "Spam/duplicate content cluster score is very high."

    if pump_risk_score >= HARD_PUMP_RISK_CEILING:
        return True, "Pump/spam risk score is extremely high."

    return False, ""
