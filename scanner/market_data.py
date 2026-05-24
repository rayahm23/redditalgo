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
    current_price: float | None = None
    avg_volume: int | None = None
    market_cap: int | None = None
    one_day_return: float | None = None
    five_day_return: float | None = None
    relative_volume: float | None = None
    above_20_day_high: bool | None = None
    analyst_target_mean: float | None = None
    analyst_target_high: float | None = None
    analyst_target_low: float | None = None
    recommendation_mean: float | None = None
    analyst_target_upside_pct: float | None = None
    analyst_target_score: float = 0.50
    analyst_target_label: str = "missing target data"

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


def analyst_target_signal(latest_price: float | None, target_mean_price: float | None) -> dict[str, Any]:
    """Return analyst target upside, bucket score, and label without overweighting targets."""

    if latest_price is None or target_mean_price is None or latest_price <= 0:
        return {
            "analyst_target_upside_pct": None,
            "analyst_target_score": 0.50,
            "analyst_target_label": "missing target data",
        }

    upside = round((target_mean_price - latest_price) / latest_price, 4)
    if upside <= -0.20:
        score, label = 0.00, "major downside"
    elif upside < -0.05:
        score, label = 0.25, "moderate downside"
    elif upside <= 0.05:
        score, label = 0.50, "near target"
    elif upside <= 0.25:
        score, label = 0.70, "moderate upside"
    elif upside <= 0.75:
        score, label = 0.90, "strong upside"
    else:
        score, label = 0.75, "extreme upside"

    return {
        "analyst_target_upside_pct": upside,
        "analyst_target_score": score,
        "analyst_target_label": label,
    }


def _history_metrics(yf_ticker: Any, avg_volume: int | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "one_day_return": None,
        "five_day_return": None,
        "relative_volume": None,
        "above_20_day_high": None,
    }
    try:
        history = yf_ticker.history(period="1mo", interval="1d", auto_adjust=False)
    except Exception:
        return metrics
    if history is None or history.empty or "Close" not in history:
        return metrics

    closes = history["Close"].dropna()
    if len(closes) >= 2 and closes.iloc[-2] > 0:
        metrics["one_day_return"] = round((closes.iloc[-1] / closes.iloc[-2]) - 1, 4)
    if len(closes) >= 6 and closes.iloc[-6] > 0:
        metrics["five_day_return"] = round((closes.iloc[-1] / closes.iloc[-6]) - 1, 4)

    if "Volume" in history and not history["Volume"].dropna().empty:
        latest_volume = _safe_number(history["Volume"].dropna().iloc[-1], integer=True)
        if latest_volume and avg_volume:
            metrics["relative_volume"] = round(latest_volume / avg_volume, 4)

    if "High" in history and len(history["High"].dropna()) >= 20:
        highs = history["High"].dropna().tail(20)
        metrics["above_20_day_high"] = bool(closes.iloc[-1] >= highs.max())

    return metrics


def get_market_data(ticker: str) -> MarketData:
    """Validate a ticker and return best-effort price, volume, cap, and trend data."""

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

        info: dict[str, Any] = {}
        try:
            info = yf_ticker.get_info()
        except Exception:
            info = {}

        current_price = _safe_number(info.get("currentPrice"))
        if current_price is not None:
            latest_price = latest_price or current_price

        if latest_price is None or avg_volume is None or market_cap is None:
            latest_price = latest_price or _safe_number(
                info.get("regularMarketPrice") or info.get("currentPrice")
            )
            avg_volume = avg_volume or _safe_number(
                info.get("averageVolume") or info.get("averageVolume10days"), integer=True
            )
            market_cap = market_cap or _safe_number(info.get("marketCap"), integer=True)

        current_price = current_price or latest_price
        analyst_target_mean = _safe_number(info.get("targetMeanPrice"))
        analyst_target_high = _safe_number(info.get("targetHighPrice"))
        analyst_target_low = _safe_number(info.get("targetLowPrice"))
        recommendation_mean = _safe_number(info.get("recommendationMean"))
        analyst_signal = analyst_target_signal(latest_price, analyst_target_mean)

        trend = _history_metrics(yf_ticker, avg_volume if isinstance(avg_volume, int) else None)
        valid = latest_price is not None or avg_volume is not None or market_cap is not None
        return MarketData(
            valid=valid,
            latest_price=latest_price,
            current_price=current_price,
            avg_volume=avg_volume if isinstance(avg_volume, int) else None,
            market_cap=market_cap if isinstance(market_cap, int) else None,
            one_day_return=trend["one_day_return"],
            five_day_return=trend["five_day_return"],
            relative_volume=trend["relative_volume"],
            above_20_day_high=trend["above_20_day_high"],
            analyst_target_mean=analyst_target_mean,
            analyst_target_high=analyst_target_high,
            analyst_target_low=analyst_target_low,
            recommendation_mean=recommendation_mean,
            analyst_target_upside_pct=analyst_signal["analyst_target_upside_pct"],
            analyst_target_score=analyst_signal["analyst_target_score"],
            analyst_target_label=analyst_signal["analyst_target_label"],
        )
    except Exception:
        return MarketData(valid=False)


def get_market_data_for_tickers(tickers: set[str] | list[str]) -> dict[str, MarketData]:
    """Fetch market data for each unique ticker symbol."""

    return {ticker: get_market_data(ticker) for ticker in sorted(set(tickers))}
