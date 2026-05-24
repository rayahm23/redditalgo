"""End-to-end Reddit stock sentiment scanner pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scanner.apify_client import fetch_apify_posts
from scanner.config import ScannerConfig
from scanner.history import calculate_historical_baselines, load_recent_history
from scanner.market_data import get_market_data_for_tickers
from scanner.reddit_client import fetch_reddit_posts
from scanner.report import write_html_reports
from scanner.scoring import aggregate_posts, rank_tickers


def write_results(results: list[dict], output_path: Path, history_dir: Path, run_date: str) -> None:
    """Write current and historical JSON outputs."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(results, indent=2) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    (history_dir / f"{run_date}.json").write_text(payload, encoding="utf-8")
    write_html_reports(results, output_path, history_dir, run_date)


def fetch_posts(config: ScannerConfig) -> list[dict]:
    """Fetch Reddit posts through the configured backend."""

    backend = config.reddit_backend.lower()
    if backend == "apify":
        return fetch_apify_posts(config)
    if backend == "praw":
        return fetch_reddit_posts(config)
    raise ValueError("REDDIT_BACKEND must be either 'apify' or 'praw'")


def run_pipeline(config: ScannerConfig | None = None) -> list[dict]:
    """Fetch Reddit data, score tickers, validate market data, and write JSON."""

    config = config or ScannerConfig.from_env()
    generated_at = datetime.now(timezone.utc).isoformat()
    run_date = generated_at[:10]

    try:
        posts = fetch_posts(config)
    except Exception as error:
        print(f"Post fetch failed; writing empty result set: {error}")
        posts = []
    aggregates = aggregate_posts(posts, excluded=config.excluded_tickers, reference_time=generated_at)
    market_data = get_market_data_for_tickers(set(aggregates.keys()))
    history_rows = load_recent_history(config.history_dir, run_date, days=7)
    baselines = calculate_historical_baselines(history_rows, days=7)
    results = rank_tickers(
        aggregates,
        market_data,
        limit=15,
        generated_at=generated_at,
        baselines=baselines,
    )
    write_results(results, config.output_path, config.history_dir, run_date)
    return results


def main() -> None:
    results = run_pipeline()
    print(f"Wrote {len(results)} ticker results to data/daily_results.json")


if __name__ == "__main__":
    main()
