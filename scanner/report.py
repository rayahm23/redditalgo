"""HTML report generation for scanner output."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def _format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"
    return f"{number:,.0f}"


def _format_price(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _risk_class(risk_flag: str) -> str:
    return {"low": "risk-low", "medium": "risk-medium", "high": "risk-high"}.get(
        risk_flag, "risk-medium"
    )


def _source_html(source: dict[str, Any]) -> str:
    title = escape(str(source.get("title") or "Untitled source"))
    subreddit = escape(str(source.get("subreddit") or "unknown"))
    permalink = str(source.get("permalink") or "")
    label = f"r/{subreddit}: {title}"
    if permalink:
        return f'<li><a href="{escape(permalink)}">{label}</a></li>'
    return f"<li>{label}</li>"


def render_results_html(results: list[dict[str, Any]]) -> str:
    """Render ranked scanner results as a readable standalone HTML document."""

    generated_at = results[0].get("generated_at") if results else "No scan results yet"
    rows = []
    for row in results:
        risk = escape(str(row.get("risk_flag") or "unknown"))
        sources = "".join(_source_html(source) for source in row.get("top_sources", []))
        rows.append(
            f"""
            <article class="card">
              <div class="rank">#{row.get("rank", "-")}</div>
              <div class="main">
                <div class="topline">
                  <h2>{escape(str(row.get("ticker", "")))}</h2>
                  <span class="score">{float(row.get("final_score", 0)):.1f}</span>
                  <span class="risk {_risk_class(risk)}">{risk} risk</span>
                </div>
                <p class="summary">{escape(str(row.get("summary", "")))}</p>
                <div class="metrics">
                  <span><b>{row.get("mention_count", 0)}</b> mentions</span>
                  <span><b>{row.get("unique_posts", 0)}</b> posts</span>
                  <span><b>{float(row.get("avg_sentiment", 0)):.2f}</b> sentiment</span>
                  <span><b>{_format_number(row.get("total_upvotes"))}</b> upvotes</span>
                  <span><b>{_format_number(row.get("comment_volume"))}</b> comments</span>
                  <span><b>{_format_price(row.get("latest_price"))}</b> price</span>
                  <span><b>{_format_number(row.get("market_cap"))}</b> market cap</span>
                  <span><b>{_format_number(row.get("avg_volume"))}</b> avg volume</span>
                </div>
                <details>
                  <summary>Top Reddit sources</summary>
                  <ul>{sources or "<li>No source links available</li>"}</ul>
                </details>
              </div>
            </article>
            """
        )

    cards = "".join(rows) or '<div class="empty">No ranked tickers yet.</div>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reddit Alpha Scanner Results</title>
  <style>
    :root {{ color-scheme: light dark; --border: #d8dee4; --muted: #656d76; --card: #ffffff; --bg: #f6f8fa; --text: #24292f; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --border: #30363d; --muted: #8b949e; --card: #161b22; --bg: #0d1117; --text: #e6edf3; }} }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 32px 18px; }}
    header {{ margin-bottom: 22px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 44px); }}
    .meta, .disclaimer {{ color: var(--muted); font-size: 14px; }}
    .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 18px 0; }}
    .toolbar a {{ color: inherit; border: 1px solid var(--border); border-radius: 999px; padding: 8px 12px; text-decoration: none; background: var(--card); }}
    .grid {{ display: grid; gap: 14px; }}
    .card {{ display: grid; grid-template-columns: 58px 1fr; gap: 14px; border: 1px solid var(--border); background: var(--card); border-radius: 16px; padding: 16px; box-shadow: 0 1px 2px rgb(0 0 0 / 5%); }}
    .rank {{ color: var(--muted); font-weight: 800; font-size: 20px; padding-top: 4px; }}
    .topline {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
    h2 {{ margin: 0; font-size: 24px; letter-spacing: 0.04em; }}
    .score {{ font-weight: 800; border-radius: 10px; padding: 5px 9px; background: #0969da; color: white; }}
    .risk {{ border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .risk-low {{ background: #dafbe1; color: #116329; }} .risk-medium {{ background: #fff8c5; color: #7d4e00; }} .risk-high {{ background: #ffebe9; color: #82071e; }}
    .summary {{ margin: 10px 0 12px; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
    .metrics span {{ border: 1px solid var(--border); border-radius: 999px; padding: 6px 9px; font-size: 13px; }}
    details {{ color: var(--muted); }} summary {{ cursor: pointer; font-weight: 650; }}
    a {{ color: #0969da; }} li {{ margin: 4px 0; }}
    .empty {{ border: 1px dashed var(--border); padding: 20px; border-radius: 12px; color: var(--muted); }}
    @media (max-width: 640px) {{ .card {{ grid-template-columns: 1fr; }} .rank {{ padding: 0; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <header>
      <h1>Reddit Alpha Scanner</h1>
      <div class="meta">Generated at: {escape(str(generated_at))}</div>
      <div class="toolbar">
        <a href="daily_results.json">Raw JSON</a>
        <a href="history/">History folder</a>
      </div>
      <p class="disclaimer">Research/watchlist tool only. Not financial advice. No auto-trading.</p>
    </header>
    <section class="grid">{cards}</section>
  </main>
</body>
</html>
"""


def write_html_reports(results: list[dict[str, Any]], output_path: Path, history_dir: Path, run_date: str) -> None:
    """Write current and historical HTML reports next to JSON outputs."""

    html = render_results_html(results)
    output_path.with_suffix(".html").write_text(html, encoding="utf-8")
    (history_dir / f"{run_date}.html").write_text(html, encoding="utf-8")
