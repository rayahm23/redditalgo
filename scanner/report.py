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


def _format_percent(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _risk_class(risk_flag: str) -> str:
    return {"low": "risk-low", "medium": "risk-medium", "high": "risk-high"}.get(
        risk_flag, "risk-medium"
    )


def _confidence_class(label: str) -> str:
    return {
        "HIGH": "chip-confidence-high",
        "MEDIUM": "chip-confidence-medium",
        "LOW": "chip-confidence-low",
    }.get(str(label).upper(), "chip-confidence-medium")


def _analyst_chip_label(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Analyst n/a"
    if value >= 0.5:
        return f"Analyst upside {_format_number(value, 2)}"
    if value > 0:
        return f"Analyst mention {_format_number(value, 2)}"
    return "Analyst quiet"


def _sparkline_svg(values: list[Any], width: int = 112, height: int = 28) -> str:
    """Render a compact inline SVG sparkline from numeric series."""

    numeric = []
    for value in values:
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(numeric) < 2:
        return ""

    minimum = min(numeric)
    maximum = max(numeric)
    span = maximum - minimum or 1.0
    step = (width - 4) / (len(numeric) - 1)
    points: list[str] = []
    for index, value in enumerate(numeric):
        x = 2 + index * step
        y = height - 2 - ((value - minimum) / span) * (height - 4)
        points.append(f"{x:.1f},{y:.1f}")

    return (
        f'<svg class="sparkline" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.75" '
        f'points="{" ".join(points)}"/></svg>'
    )


def _trend_block(label: str, values: list[Any]) -> str:
    svg = _sparkline_svg(values)
    if not svg:
        return ""
    return f'<div class="trend"><span class="trend-label">{escape(label)}</span>{svg}</div>'


def _source_html(source: dict[str, Any]) -> str:
    title = escape(str(source.get("title") or "Untitled source"))
    subreddit = escape(str(source.get("subreddit") or "unknown"))
    post_type = escape(str(source.get("post_type") or ""))
    permalink = str(source.get("permalink") or "")
    weight = source.get("recency_weight")
    meta = []
    if post_type:
        meta.append(post_type)
    if weight is not None:
        meta.append(f"weight {float(weight):.2f}")
    meta_text = f" <span class=\"muted\">({', '.join(meta)})</span>" if meta else ""
    label = f"r/{subreddit}: {title}{meta_text}"
    if permalink:
        return f'<li><a href="{escape(permalink)}">{label}</a></li>'
    return f"<li>{label}</li>"


def _breakdown_html(breakdown: dict[str, Any]) -> str:
    if not breakdown:
        return "<p>No score breakdown available for this run.</p>"
    parts = [
        ("Attention acceleration", breakdown.get("attention_acceleration_score")),
        ("Engagement quality", breakdown.get("engagement_quality_score")),
        ("Sentiment", breakdown.get("sentiment_score")),
        ("Net conviction", breakdown.get("net_conviction_score")),
        ("Market confirmation", breakdown.get("market_confirmation_score")),
        ("Subreddit spread", breakdown.get("subreddit_spread_score")),
        ("Pump risk penalty", breakdown.get("pump_risk_penalty")),
        ("Raw score 0-1", breakdown.get("raw_score_0_to_1")),
    ]
    items = "".join(f"<li><b>{escape(label)}:</b> {_format_number(value, 4)}</li>" for label, value in parts)
    formula = escape(str(breakdown.get("formula", "")))
    return f"""
      <ul class="breakdown-list">{items}</ul>
      <p class="muted"><b>Formula:</b> {formula}</p>
    """


def _list_html(items: list[Any], fallback: str) -> str:
    if not items:
        return f"<li>{escape(fallback)}</li>"
    return "".join(f"<li>{escape(str(item))}</li>" for item in items)


def render_results_html(results: list[dict[str, Any]]) -> str:
    """Render ranked scanner results as a readable standalone HTML document."""

    generated_at = results[0].get("generated_at") if results else "No scan results yet"
    rows = []
    for row in results:
        risk = escape(str(row.get("risk_flag") or "unknown"))
        recommendation = escape(str(row.get("recommendation_type") or "Watchlist"))
        confidence_label = str(row.get("signal_confidence_label") or "n/a")
        confidence = escape(confidence_label)
        confidence_class = _confidence_class(confidence_label)
        catalyst = escape(str(row.get("catalyst_type") or row.get("dominant_post_type") or "Other"))
        analyst_chip = escape(_analyst_chip_label(row.get("analyst_target_score")))
        trends = row.get("historical_trends") or {}
        sparklines = row.get("sparklines") or trends
        trend_html = "".join(
            [
                _trend_block("Mentions", sparklines.get("mentions") or trends.get("mentions_7d", [])),
                _trend_block("Sentiment", sparklines.get("sentiment") or trends.get("sentiment_7d", [])),
                _trend_block("Score", sparklines.get("score") or trends.get("score_7d", [])),
                _trend_block(
                    "Analyst upside",
                    sparklines.get("analyst_target_upside")
                    or trends.get("analyst_target_upside_7d", []),
                ),
            ]
        )
        sources = "".join(_source_html(source) for source in row.get("top_sources", []))
        rows.append(
            f"""
            <article class="card">
              <div class="rank">#{row.get("rank", "-")}</div>
              <div class="main">
                <div class="topline">
                  <h2>{escape(str(row.get("ticker", "")))}</h2>
                  <span class="score">{float(row.get("final_score", 0)):.1f}</span>
                  <span class="recommendation">{recommendation}</span>
                  <span class="risk {_risk_class(risk)}">{risk} risk</span>
                </div>
                <div class="chips">
                  <span class="chip chip-analyst">{analyst_chip}</span>
                  <span class="chip {confidence_class}">{confidence} confidence</span>
                  <span class="chip chip-catalyst">{catalyst} catalyst</span>
                </div>
                <p class="summary">{escape(str(row.get("summary", "")))}</p>
                {f'<div class="trends">{trend_html}</div>' if trend_html else ''}
                <div class="metrics">
                  <span><b>{row.get("mention_count", 0)}</b> mentions</span>
                  <span><b>{_format_number(row.get("attention_acceleration"), 2)}x</b> acceleration</span>
                  <span><b>{_format_number(row.get("seven_day_avg_mentions"), 2)}</b> 7d avg mentions</span>
                  <span><b>{row.get("unique_posts", 0)}</b> posts</span>
                  <span><b>{row.get("unique_subreddits", 0)}</b> subreddits</span>
                  <span><b>{escape(str(row.get("dominant_post_type") or "Other"))}</b> type</span>
                  <span><b>{float(row.get("avg_sentiment", 0)):.2f}</b> sentiment</span>
                  <span><b>{_format_number(row.get("net_conviction_score"), 2)}</b> conviction</span>
                  <span><b>{_format_number(row.get("market_confirmation_score"), 2)}</b> market confirm</span>
                  <span><b>{_format_number(row.get("pump_risk_score"), 2)}</b> pump risk</span>
                  <span><b>{_format_price(row.get("latest_price"))}</b> price</span>
                  <span><b>{_format_percent(row.get("one_day_return"))}</b> 1d</span>
                  <span><b>{_format_percent(row.get("five_day_return"))}</b> 5d</span>
                  <span><b>{_format_number(row.get("relative_volume"), 2)}</b> rel vol</span>
                </div>
                <details open>
                  <summary>Score breakdown</summary>
                  {_breakdown_html(row.get("score_breakdown") or {})}
                </details>
                <details>
                  <summary>Risk explanation</summary>
                  <p>{escape(str(row.get("risk_explanation") or ""))}</p>
                  <ul>{_list_html(row.get("risk_reasons") or [], "No risk reason details available.")}</ul>
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
    .recommendation {{ border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 700; background: #ddf4ff; color: #0550ae; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 4px; }}
    .chip {{ border-radius: 999px; padding: 4px 9px; font-size: 11px; font-weight: 650; border: 1px solid var(--border); background: var(--bg); }}
    .chip-analyst {{ background: #fbefff; color: #6e40c9; border-color: #d8b9ff; }}
    .chip-catalyst {{ background: #fff8e6; color: #7a4c00; border-color: #f0d59b; }}
    .chip-confidence-high {{ background: #dafbe1; color: #116329; border-color: #aceebb; }}
    .chip-confidence-medium {{ background: #fff8c5; color: #7d4e00; border-color: #f0e68c; }}
    .chip-confidence-low {{ background: #ffebe9; color: #82071e; border-color: #ffbbb9; }}
    .trends {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin: 8px 0 10px; }}
    .trend {{ border: 1px solid var(--border); border-radius: 10px; padding: 6px 8px; color: #0969da; }}
    .trend-label {{ display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; }}
    .sparkline {{ display: block; width: 100%; height: auto; }}
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
      <div class="toolbar"><a href="daily_results.json">Raw JSON</a><a href="history/">History folder</a></div>
      <p class="disclaimer">Research/watchlist tool only. Not financial advice. Mentions are filtered to the last 7 days, compared with historical baselines, and penalized for pump/noise risk.</p>
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
