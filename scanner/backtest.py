"""Basic forward-return backtesting for prior scanner outputs."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf

BACKTEST_OUTPUT = Path("data/backtest_results.json")
HISTORY_DIR = Path("data/history")


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


def _closing_prices(symbol: str, start: date, end: date) -> list[float]:
    try:
        history = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(), interval="1d", auto_adjust=True)
    except Exception:
        return []
    if history is None or history.empty or "Close" not in history:
        return []
    return [float(value) for value in history["Close"].dropna().tolist()]


def _backtest_row(scan_date: date, row: dict[str, Any], spy_prices: list[float]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    prices = _closing_prices(ticker, scan_date, scan_date + timedelta(days=14))
    next_day = _safe_return(prices, 0, 1)
    three_day = _safe_return(prices, 0, 3)
    seven_day = _safe_return(prices, 0, 7)
    spy_seven = _safe_return(spy_prices, 0, 7)
    spy_relative = round(seven_day - spy_seven, 4) if seven_day is not None and spy_seven is not None else None
    return {
        "scan_date": scan_date.isoformat(),
        "ticker": ticker,
        "rank": row.get("rank"),
        "final_score": row.get("final_score"),
        "recommendation_type": row.get("recommendation_type"),
        "next_day_return": next_day,
        "three_day_return": three_day,
        "seven_day_return": seven_day,
        "spy_relative_return": spy_relative,
    }


def run_backtest(history_dir: Path = HISTORY_DIR, output_path: Path = BACKTEST_OUTPUT) -> list[dict[str, Any]]:
    """Read historical scanner files and write best-effort forward returns."""

    results: list[dict[str, Any]] = []
    if not history_dir.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("[]\n", encoding="utf-8")
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
        spy_prices = _closing_prices("SPY", scan_date, scan_date + timedelta(days=14))
        for row in rows:
            if isinstance(row, dict) and row.get("ticker"):
                try:
                    results.append(_backtest_row(scan_date, row, spy_prices))
                except Exception as error:
                    results.append(
                        {
                            "scan_date": scan_date.isoformat(),
                            "ticker": str(row.get("ticker") or "").upper(),
                            "error": str(error),
                        }
                    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> None:
    try:
        results = run_backtest()
        print(f"Wrote {len(results)} backtest rows to {BACKTEST_OUTPUT}")
    except Exception as error:
        # Backtesting is diagnostic and should not fail scheduled scans.
        print(f"Backtest skipped: {error}")


if __name__ == "__main__":
    main()
