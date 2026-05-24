"""Ticker validation and market data lookup with yfinance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import yfinance as yf


@dataclass(frozen=True)
class MarketData:
    """Market fields used by the scanner scoring model."""

    valid: bool
    latest_price: float | None = None
    avg_volume: int | None = None
    market_cap: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_number(value: Any, integer: bool = False) -> float | int | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return int(number) if integer else round(number, 4)


def _fast_info_value(fast_info: Any, *keys: str) -> Any:
    for key in keys:
        try:
            value = fast_info.get(key)
        except AttributeError:
            try:
                value = getattr(fast_info, key)
            except AttributeError:
                value = None
        if value not in (None, ""):
            return value
    return None


def get_market_data(ticker: str) -> MarketData:
    """Validate a ticker and return best-effort price, volume, and cap data."""

    symbol = ticker.upper()
    try:
        yf_ticker = yf.Ticker(symbol)
        fast_info = yf_ticker.fast_info

        latest_price = _safe_number(
            _fast_info_value(fast_info, "last_price", "lastPrice", "regularMarketPrice")
        )
        avg_volume = _safe_number(
            _fast_info_value(
                fast_info,
                "three_month_average_volume",
                "threeMonthAverageVolume",
                "ten_day_average_volume",
                "tenDayAverageVolume",
            ),
            integer=True,
        )
        market_cap = _safe_number(
            _fast_info_value(fast_info, "market_cap", "marketCap"), integer=True
        )

        if latest_price is None or avg_volume is None or market_cap is None:
            info: dict[str, Any] = {}
            try:
                info = yf_ticker.get_info()
            except Exception:
                info = {}
            latest_price = latest_price or _safe_number(
                info.get("regularMarketPrice") or info.get("currentPrice")
            )
            avg_volume = avg_volume or _safe_number(
                info.get("averageVolume") or info.get("averageVolume10days"), integer=True
            )
            market_cap = market_cap or _safe_number(info.get("marketCap"), integer=True)

        valid = latest_price is not None or avg_volume is not None or market_cap is not None
        return MarketData(
            valid=valid,
            latest_price=latest_price,
            avg_volume=avg_volume,
            market_cap=market_cap,
        )
    except Exception:
        return MarketData(valid=False)


def get_market_data_for_tickers(tickers: set[str] | list[str]) -> dict[str, MarketData]:
    """Fetch market data for each unique ticker symbol."""

    return {ticker: get_market_data(ticker) for ticker in sorted(set(tickers))}
