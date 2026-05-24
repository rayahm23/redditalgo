"""End-to-end Reddit stock sentiment scanner pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scanner.config import ScannerConfig
from scanner.market_data import get_market_data_for_tickers
from scanner.reddit_client import fetch_reddit_posts
from scanner.scoring import aggregate_posts, rank_tickers


def write_results(results: list[dict], output_path: Path, history_dir: Path, run_date: str) -> None:
    """Write current and historical JSON outputs."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(results, indent=2) + "
"
    output_path.write_text(payload, encoding="utf-8")
    (history_dir / f"{run_date}.json").write_text(payload, encoding="utf-8")


def run_pipeline(config: ScannerConfig | None = None) -> list[dict]:
    """Fetch Reddit data, score tickers, validate market data, and write JSON."""

    config = config or ScannerConfig.from_env()
    generated_at = datetime.now(timezone.utc).isoformat()
    run_date = generated_at[:10]

    posts = fetch_reddit_posts(config)
    aggregates = aggregate_posts(posts, excluded=config.excluded_tickers)
    market_data = get_market_data_for_tickers(set(aggregates.keys()))
    results = rank_tickers(aggregates, market_data, limit=15, generated_at=generated_at)
    write_results(results, config.output_path, config.history_dir, run_date)
    return results


def main() -> None:
    results = run_pipeline()
    print(f"Wrote {len(results)} ticker results to data/daily_results.json")


if __name__ == "__main__":
    main()
