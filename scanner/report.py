"""HTML report generation for scanner output."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def _format_number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.{digits}f}B"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.{digits}f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.{digits}f}K"
    if number.is_integer():
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


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
    weight = source.get("recency_weight")
    weight_text = f" <span class=\"muted\">(weight {float(weight):.2f})</span>" if weight is not None else ""
    label = f"r/{subreddit}: {title}{weight_text}"
    if permalink:
        return f'<li><a href="{escape(permalink)}">{label}</a></li>'
    return f"<li>{label}</li>"


def _breakdown_html(breakdown: dict[str, Any]) -> str:
    if not breakdown:
        return "<p>No score breakdown available for this run.</p>"
    parts = [
        ("Attention", breakdown.get("attention_score")),
        ("Engagement", breakdown.get("engagement_score")),
        ("Sentiment", breakdown.get("sentiment_score")),
        ("Market validity bonus", breakdown.get("market_validity_bonus")),
        ("Risk penalty", breakdown.get("risk_penalty")),
        ("Raw before cap", breakdown.get("raw_score_before_cap")),
        ("Capped before risk", breakdown.get("capped_score_before_risk")),
    ]
    items = "".join(f"<li><b>{escape(label)}:</b> {_format_number(value, 2)}</li>" for label, value in parts)
    formula = escape(str(breakdown.get("formula", "")))
    weights = breakdown.get("recency_weights") or []
    weight_text = ", ".join(str(weight) for weight in weights)
    return f"""
      <ul class="breakdown-list">{items}</ul>
      <p class="muted"><b>Formula:</b> {formula}</p>
      <p class="muted"><b>7-day recency weights:</b> today through day 6 = {escape(weight_text)}</p>
    """


def _risk_reasons_html(row: dict[str, Any]) -> str:
    reasons = row.get("risk_reasons") or []
    if not reasons:
        return "<li>No risk reason details available for this run.</li>"
    return "".join(f"<li>{escape(str(reason))}</li>" for reason in reasons)


def render_results_html(results: list[dict[str, Any]]) -> str:
    """Render ranked scanner results as a readable standalone HTML document."""

    generated_at = results[0].get("generated_at") if results else "No scan results yet"
    rows = []
    for row in results:
        risk = escape(str(row.get("risk_flag") or "unknown"))
        sources = "".join(_source_html(source) for source in row.get("top_sources", []))
        weighted_mentions = row.get("weighted_mention_count", row.get("mention_count", 0))
        weighted_posts = row.get("weighted_unique_posts", row.get("unique_posts", 0))
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
                  <span><b>{row.get("mention_count", 0)}</b> raw mentions</span>
                  <span><b>{_format_number(weighted_mentions, 2)}</b> weighted mentions</span>
                  <span><b>{row.get("unique_posts", 0)}</b> posts</span>
                  <span><b>{_format_number(weighted_posts, 2)}</b> weighted posts</span>
                  <span><b>{float(row.get("avg_sentiment", 0)):.2f}</b> sentiment</span>
                  <span><b>{_format_number(row.get("total_upvotes"))}</b> upvotes</span>
                  <span><b>{_format_number(row.get("comment_volume"))}</b> comments</span>
                  <span><b>{_format_price(row.get("latest_price"))}</b> price</span>
                  <span><b>{_format_number(row.get("market_cap"))}</b> market cap</span>
                  <span><b>{_format_number(row.get("avg_volume"))}</b> avg volume</span>
                </div>
                <details open>
                  <summary>Score breakdown</summary>
                  {_breakdown_html(row.get("score_breakdown") or {})}
                </details>
                <details>
                  <summary>Risk explanation</summary>
                  <ul>{_risk_reasons_html(row)}</ul>
                </details>
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
    .meta, .disclaimer, .muted {{ color: var(--muted); font-size: 14px; }}
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
    details {{ color: var(--muted); margin-top: 8px; }} summary {{ cursor: pointer; font-weight: 650; color: var(--text); }}
    .breakdown-list {{ columns: 2; }}
    a {{ color: #0969da; }} li {{ margin: 4px 0; }}
    .empty {{ border: 1px dashed var(--border); padding: 20px; border-radius: 12px; color: var(--muted); }}
    @media (max-width: 640px) {{ .card {{ grid-template-columns: 1fr; }} .rank {{ padding: 0; }} .breakdown-list {{ columns: 1; }} }}
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
      <p class="disclaimer">Research/watchlist tool only. Not financial advice. Mentions are filtered to the last 7 days and weighted by recency.</p>
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
