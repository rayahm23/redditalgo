"""Forward-return backtesting for historical scanner signals."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf

BACKTEST_OUTPUT = Path("data/backtest_results.json")
BACKTEST_SUMMARY_OUTPUT = Path("data/backtest_summary.json")
HISTORY_DIR = Path("data/history")
FORWARD_WINDOWS = (1, 3, 7, 30)


def _parse_history_date(path: Path) -> date | None:
    try:
        return datetime.strptime(path.stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_return(prices: list[float], start_idx: int, end_idx: int) -> float | None:
    try:
        start = float(prices[start_idx])
        end = float(prices[end_idx])
    except (IndexError, TypeError, ValueError):
        return None
    if start <= 0:
        return None
    return round((end / start) - 1, 4)


def _max_drawdown(prices: list[float], start_idx: int, end_idx: int) -> float | None:
    try:
        window = [float(prices[index]) for index in range(start_idx, end_idx + 1)]
    except (IndexError, TypeError, ValueError):
        return None
    if len(window) < 2:
        return None
    peak = window[0]
    worst = 0.0
    for price in window:
        peak = max(peak, price)
        if peak > 0:
            worst = min(worst, (price / peak) - 1)
    return round(worst, 4)


def _closing_prices(symbol: str, start: date, end: date) -> list[float]:
    try:
        history = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=True,
        )
    except Exception:
        return []
    if history is None or history.empty or "Close" not in history:
        return []
    return [float(value) for value in history["Close"].dropna().tolist()]


def _pending_reason(trading_days_available: int, window: int) -> str | None:
    if trading_days_available <= window:
        return "Not enough forward data yet"
    return None


def _backtest_signal(scan_date: date, row: dict[str, Any], spy_prices: list[float]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    prices = _closing_prices(ticker, scan_date, scan_date + timedelta(days=45))
    trading_days = max(len(prices) - 1, 0)

    payload: dict[str, Any] = {
        "scan_date": scan_date.isoformat(),
        "generated_at": row.get("generated_at"),
        "ticker": ticker,
        "rank": row.get("rank"),
        "final_score": row.get("final_score"),
        "signal_score_at_signal": row.get("signal_score_at_signal", row.get("final_score")),
        "price_at_signal": row.get("price_at_signal", row.get("latest_price")),
        "recommendation_type": row.get("recommendation_type"),
        "confidence_label": row.get("signal_confidence_label"),
        "sector_group": row.get("sector_group"),
        "under_15_flag": row.get("under_15_flag"),
        "alerts": row.get("alerts", []),
        "pending": False,
        "pending_reason": None,
        "error": None,
    }

    if not prices:
        payload["pending"] = True
        payload["pending_reason"] = "Price history unavailable"
        return payload

    for window in FORWARD_WINDOWS:
        key = f"return_{window}d"
        pending = _pending_reason(trading_days, window)
        if pending:
            payload[key] = None
            if window == FORWARD_WINDOWS[0]:
                payload["pending"] = True
                payload["pending_reason"] = pending
        else:
            payload[key] = _safe_return(prices, 0, window)

    spy_returns: dict[str, float | None] = {}
    for window in FORWARD_WINDOWS:
        spy_returns[window] = _safe_return(spy_prices, 0, window) if spy_prices else None
        rel_key = f"spy_relative_{window}d"
        ticker_return = payload.get(f"return_{window}d")
        spy_return = spy_returns[window]
        if ticker_return is not None and spy_return is not None:
            payload[rel_key] = round(ticker_return - spy_return, 4)
        else:
            payload[rel_key] = None

    for window in (7, 30):
        pending = _pending_reason(trading_days, window)
        drawdown_key = f"max_drawdown_{window}d"
        if pending:
            payload[drawdown_key] = None
        else:
            payload[drawdown_key] = _max_drawdown(prices, 0, window)

    return payload


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _win_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values), 4)


def _group_performance(results: list[dict[str, Any]], key: str, return_key: str = "return_7d") -> dict[str, Any]:
    buckets: dict[str, list[float]] = {}
    for row in results:
        if row.get("pending") or row.get(return_key) is None:
            continue
        label = str(row.get(key) or "unknown")
        buckets.setdefault(label, []).append(float(row[return_key]))
    return {
        label: {"count": len(values), "avg_return": _mean(values), "win_rate": _win_rate(values)}
        for label, values in buckets.items()
    }


def _performance_by_alert_type(results: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[float]] = {}
    for row in results:
        if row.get("pending") or row.get("return_7d") is None:
            continue
        for alert in row.get("alerts") or []:
            buckets.setdefault(str(alert), []).append(float(row["return_7d"]))
    return {
        alert: {"count": len(values), "avg_return": _mean(values), "win_rate": _win_rate(values)}
        for alert, values in buckets.items()
    }


def build_backtest_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate completed vs pending backtest rows."""

    completed = [row for row in results if not row.get("pending") and not row.get("error")]
    pending = [row for row in results if row.get("pending")]

    def completed_returns(key: str) -> list[float]:
        values = []
        for row in completed:
            value = row.get(key)
            if value is not None:
                values.append(float(value))
        return values

    summary: dict[str, Any] = {
        "total_signals": len(results),
        "total_completed_signals": len(completed),
        "total_pending_signals": len(pending),
        "avg_1d_return": _mean(completed_returns("return_1d")),
        "avg_3d_return": _mean(completed_returns("return_3d")),
        "avg_7d_return": _mean(completed_returns("return_7d")),
        "avg_30d_return": _mean(completed_returns("return_30d")),
        "win_rate_1d": _win_rate(completed_returns("return_1d")),
        "win_rate_7d": _win_rate(completed_returns("return_7d")),
        "win_rate_30d": _win_rate(completed_returns("return_30d")),
        "avg_spy_relative_7d": _mean(completed_returns("spy_relative_7d")),
        "performance_by_recommendation_type": _group_performance(results, "recommendation_type"),
        "performance_by_confidence_label": _group_performance(results, "confidence_label"),
        "performance_by_sector_group": _group_performance(results, "sector_group"),
        "performance_by_under_15_flag": _group_performance(results, "under_15_flag"),
        "performance_by_alert_type": _performance_by_alert_type(results),
        "message": None,
    }
    if not results:
        summary["message"] = "No historical signals yet. Run the daily scanner to start collecting forward-history."
    elif len(completed) < 5:
        summary["message"] = "More daily history is needed before backtest statistics are meaningful."
    return summary


def run_backtest(
    history_dir: Path = HISTORY_DIR,
    output_path: Path = BACKTEST_OUTPUT,
    summary_path: Path = BACKTEST_SUMMARY_OUTPUT,
) -> list[dict[str, Any]]:
    """Read historical scanner files and write forward-return results."""

    results: list[dict[str, Any]] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not history_dir.exists():
        summary = build_backtest_summary(results)
        output_path.write_text("[]\n", encoding="utf-8")
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return results

    for path in sorted(history_dir.glob("*.json")):
        scan_date = _parse_history_date(path)
        if scan_date is None:
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        spy_prices = _closing_prices("SPY", scan_date, scan_date + timedelta(days=45))
        for row in rows:
            if not isinstance(row, dict) or not row.get("ticker"):
                continue
            if row.get("excluded"):
                continue
            try:
                results.append(_backtest_signal(scan_date, row, spy_prices))
            except Exception as error:
                results.append(
                    {
                        "scan_date": scan_date.isoformat(),
                        "ticker": str(row.get("ticker") or "").upper(),
                        "pending": True,
                        "pending_reason": "Backtest error",
                        "error": str(error),
                    }
                )

    summary = build_backtest_summary(results)
    output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> None:
    try:
        results = run_backtest()
        print(f"Wrote {len(results)} backtest rows to {BACKTEST_OUTPUT}")
        print(f"Wrote summary to {BACKTEST_SUMMARY_OUTPUT}")
    except Exception as error:
        print(f"Backtest skipped: {error}")


if __name__ == "__main__":
    main()
