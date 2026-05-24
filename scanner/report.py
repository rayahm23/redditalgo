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


def _format_price(value: Any, *, compact: bool = False) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if compact and number >= 1000:
        return f"${_format_number(number, 0)}"
    return f"${number:,.2f}"


def _format_percent(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    try:
        pct = float(value) * 100
    except (TypeError, ValueError):
        return "n/a"
    if signed and pct > 0:
        return f"+{pct:.0f}%"
    if signed and pct < 0:
        return f"{pct:.0f}%"
    return f"{pct:.2f}%"


def _risk_label(risk_flag: str) -> str:
    return {
        "low": "Liquid profile",
        "medium": "Investable",
        "high": "Illiquid / low-quality",
    }.get(str(risk_flag).lower(), "Investable")


def _strength_class(tier: str) -> str:
    return {
        "Strong": "tier-strong",
        "Moderate": "tier-moderate",
        "Weak": "tier-weak",
    }.get(tier, "tier-moderate")


def _analyst_target_html(row: dict[str, Any]) -> str:
    """Render street analyst target vs current price (not Reddit language score)."""

    target = row.get("analyst_target_mean")
    upside = row.get("analyst_target_upside_pct")
    if target is None or upside is None:
        return '<span class="analyst-target analyst-neutral">Street target unavailable</span>'

    price_text = _format_price(target, compact=True)
    pct_text = _format_percent(upside, signed=True)
    if upside > 0.02:
        css = "analyst-upside"
    elif upside < -0.02:
        css = "analyst-downside"
    else:
        css = "analyst-neutral"
    return (
        f'<span class="analyst-target {css}">'
        f"{escape(price_text)} avg target ({escape(pct_text)})"
        f"</span>"
    )


def _meta_line(row: dict[str, Any]) -> str:
    confidence = str(row.get("signal_confidence_label") or "n/a").title()
    catalyst = str(row.get("catalyst_type") or row.get("dominant_post_type") or "Mixed")
    if catalyst.lower() == "mixed":
        catalyst_label = "Mixed Catalyst"
    else:
        catalyst_label = f"{catalyst} Catalyst"
    risk = _risk_label(str(row.get("risk_flag") or "medium"))
    return escape(f"{confidence} Confidence • {catalyst_label} • {risk}")


def _sparkline_svg(values: list[Any], width: int = 88, height: int = 22) -> str:
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
    points = []
    for index, value in enumerate(numeric):
        x = 2 + index * step
        y = height - 2 - ((value - minimum) / span) * (height - 4)
        points.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg class="sparkline" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.5" '
        f'points="{" ".join(points)}"/></svg>'
    )


def _signal_summary_html(row: dict[str, Any]) -> str:
    summaries = row.get("signal_summaries") or {}
    labels = {
        "retail_attention": "Retail Attention",
        "discussion_quality": "Discussion Quality",
        "market_confirmation": "Market Confirmation",
        "speculation_risk": "Speculation Risk",
        "analyst_outlook": "Analyst Outlook",
    }
    items = []
    for key, label in labels.items():
        tier = str(summaries.get(key) or "Moderate")
        if key == "speculation_risk":
            css = {
                "Strong": "tier-risk-high",
                "Moderate": "tier-moderate",
                "Weak": "tier-risk-low",
            }.get(tier, "tier-moderate")
        else:
            css = _strength_class(tier)
        items.append(
            f'<div class="signal-row"><span>{escape(label)}</span>'
            f'<span class="signal-tier {css}">{escape(tier)}</span></div>'
        )
    return "".join(items)


def _key_metrics_html(row: dict[str, Any]) -> str:
    accel = row.get("attention_acceleration")
    five_day = row.get("five_day_return")
    upside = row.get("analyst_target_upside_pct")
    subs = row.get("unique_subreddits", 0)
    risk = _risk_label(str(row.get("risk_flag") or "medium"))

    accel_text = f"{_format_number(accel, 1)}x mention acceleration"
    five_day_text = f"{_format_percent(five_day, signed=True)} 5d"
    if upside is not None:
        upside_text = f"{_format_percent(upside, signed=True)} to avg target"
    else:
        upside_text = "Target data n/a"
    spread_text = f"{subs} subreddit{'s' if int(subs or 0) != 1 else ''}"

    return f"""
      <div class="key-metrics">
        <div><span class="metric-label">Attention</span><span class="metric-value">{escape(accel_text)}</span></div>
        <div><span class="metric-label">5D Performance</span><span class="metric-value">{escape(five_day_text)}</span></div>
        <div><span class="metric-label">Analyst Upside</span><span class="metric-value">{escape(upside_text)}</span></div>
        <div><span class="metric-label">Investability</span><span class="metric-value">{escape(risk)}</span></div>
        <div><span class="metric-label">Spread</span><span class="metric-value">{escape(spread_text)}</span></div>
      </div>
    """


def _human_breakdown_html(breakdown: dict[str, Any], row: dict[str, Any]) -> str:
    if not breakdown:
        return "<p>No score breakdown available for this run.</p>"

    def label(score: Any, *, positive: bool = True) -> str:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return "n/a"
        if positive:
            if value >= 0.65:
                return "Strong"
            if value >= 0.4:
                return "Moderate"
            return "Weak"
        if value >= 0.65:
            return "Elevated"
        if value >= 0.4:
            return "Moderate"
        return "Low"

    items = [
        ("Retail attention", label(breakdown.get("attention_acceleration_score"))),
        ("Discussion quality", label(breakdown.get("engagement_quality_score"))),
        ("Sentiment tone", label(breakdown.get("sentiment_score"))),
        ("Conviction", label(breakdown.get("net_conviction_score"))),
        ("Market confirmation", label(breakdown.get("market_confirmation_score"))),
        ("Subreddit breadth", label(breakdown.get("subreddit_spread_score"))),
        ("Speculative activity", label(row.get("pump_risk_score"), positive=False)),
    ]
    readable = "".join(
        f"<li><span>{escape(name)}</span><strong>{escape(value)}</strong></li>" for name, value in items
    )
    formula = escape(str(breakdown.get("formula", "")))
    raw = breakdown.get("raw_score_0_to_1")
    final = breakdown.get("final_score")
    return f"""
      <ul class="readable-breakdown">{readable}</ul>
      <details class="nested-details">
        <summary>Algorithm details</summary>
        <ul class="telemetry">
          <li><b>Raw model score:</b> {_format_number(raw, 3)}</li>
          <li><b>Normalized score:</b> {_format_number(final, 1)}</li>
          <li><b>Pump penalty:</b> {_format_number(breakdown.get('pump_risk_penalty'), 3)}</li>
        </ul>
        <p class="muted"><b>Formula:</b> {formula}</p>
      </details>
    """


def _secondary_metrics_html(row: dict[str, Any]) -> str:
    parts = [
        ("Mentions", str(row.get("mention_count", 0))),
        ("Posts", str(row.get("unique_posts", 0))),
        ("Sentiment tone", _sentiment_label(row.get("avg_sentiment"))),
        ("Conviction", _conviction_label(row.get("net_conviction_score"))),
        ("Market confirm", _market_label(row.get("market_confirmation_score"))),
        ("Speculation", _pump_label(row.get("pump_risk_score"))),
        ("Rel volume", _format_number(row.get("relative_volume"), 1)),
        ("Price", _format_price(row.get("latest_price"), compact=True)),
    ]
    return "".join(
        f"<span><b>{escape(label)}:</b> {escape(value)}</span>" for label, value in parts
    )


def _sentiment_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if score >= 0.25:
        return "Positive"
    if score <= -0.25:
        return "Negative"
    return "Mixed"


def _conviction_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if score >= 0.65:
        return "Bullish lean"
    if score <= 0.35:
        return "Bearish lean"
    return "Balanced"


def _market_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if score >= 0.6:
        return "Confirmed"
    if score >= 0.35:
        return "Partial"
    return "Weak"


def _pump_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if score >= 0.55:
        return "Elevated"
    if score >= 0.3:
        return "Moderate"
    return "Low"


def _catalyst_strength_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "Unclear"
    if score >= 0.7:
        return "Well-defined"
    if score >= 0.45:
        return "Emerging"
    return "Diffuse"


def _theme_list_html(themes: list[Any], empty: str = "None identified") -> str:
    if not themes:
        return f"<li>{escape(empty)}</li>"
    return "".join(f"<li>{escape(str(theme))}</li>" for theme in themes[:4])


def _narrative_html(row: dict[str, Any]) -> str:
    primary = escape(str(row.get("primary_narrative") or "No clear narrative identified."))
    bullish = _theme_list_html(row.get("bullish_themes") or [])
    bearish = _theme_list_html(row.get("bearish_themes") or [], empty="No major bearish themes")
    keywords = row.get("narrative_keywords") or []
    keyword_text = ", ".join(escape(str(word)) for word in keywords[:6])
    return f"""
      <section class="narrative-panel">
        <h3>Discussion Summary</h3>
        <p class="primary-narrative">{primary}</p>
        <div class="theme-columns">
          <div>
            <h4>Bullish Themes</h4>
            <ul>{bullish}</ul>
          </div>
          <div>
            <h4>Bearish Themes</h4>
            <ul>{bearish}</ul>
          </div>
        </div>
        <details class="nested-details">
          <summary>Narrative keywords</summary>
          <p class="muted">{keyword_text or "n/a"}</p>
        </details>
      </section>
    """


def _catalyst_details_html(row: dict[str, Any]) -> str:
    dominant = escape(str(row.get("dominant_post_type") or "Other"))
    catalyst = escape(str(row.get("catalyst_type") or row.get("dominant_post_type") or "Mixed"))
    strength = escape(_catalyst_strength_label(row.get("catalyst_confidence_score")))
    recommendation = str(row.get("recommendation_type") or "")
    narrative = (
        "Discussion is leaning into AI-linked narratives."
        if "AI" in recommendation
        else "Earnings/guidance language is shaping the conversation."
        if dominant == "Earnings" or catalyst == "Earnings"
        else "The catalyst is broad and not dominated by a single event type."
    )
    return f"""
      <ul class="catalyst-details">
        <li><span>Primary post theme</span><strong>{dominant}</strong></li>
        <li><span>Catalyst label</span><strong>{catalyst}</strong></li>
        <li><span>Catalyst clarity</span><strong>{strength}</strong></li>
      </ul>
      <p class="muted">{escape(narrative)}</p>
    """


def _trends_detail_html(row: dict[str, Any]) -> str:
    trends = row.get("historical_trends") or {}
    dates = row.get("trend_dates") or []
    if not trends.get("mentions_7d"):
        return "<p class='muted'>Historical trend data will populate after several daily scans.</p>"

    def series_rows(key: str, label: str) -> str:
        values = trends.get(key) or []
        cells = []
        for index, value in enumerate(values):
            day = escape(dates[index]) if index < len(dates) else f"D{index + 1}"
            cells.append(f"<li><span>{day}</span><span>{_format_number(value, 2)}</span></li>")
        return f"<div><h4>{escape(label)}</h4><ul class='trend-series'>{''.join(cells)}</ul></div>"

    return (
        series_rows("mentions_7d", "Mentions")
        + series_rows("score_7d", "Score")
        + series_rows("sentiment_7d", "Sentiment")
        + series_rows("analyst_target_upside_7d", "Reddit analyst-language index")
    )


def _source_html(source: dict[str, Any]) -> str:
    title = escape(str(source.get("title") or "Untitled source"))
    subreddit = escape(str(source.get("subreddit") or "unknown"))
    post_type = escape(str(source.get("post_type") or ""))
    permalink = str(source.get("permalink") or "")
    label = f"r/{subreddit}: {title}"
    meta = f' <span class="muted">({post_type})</span>' if post_type else ""
    if permalink:
        return f'<li><a href="{escape(permalink)}">{label}{meta}</a></li>'
    return f"<li>{label}{meta}</li>"


def _list_html(items: list[Any], fallback: str) -> str:
    if not items:
        return f"<li>{escape(fallback)}</li>"
    return "".join(f"<li>{escape(str(item))}</li>" for item in items)


def _card_html(row: dict[str, Any]) -> str:
    ticker = escape(str(row.get("ticker", "")))
    recommendation = escape(str(row.get("recommendation_type") or "Watchlist"))
    confidence = escape(str(row.get("signal_confidence_label") or "n/a").title())
    summary = escape(str(row.get("summary") or ""))
    trends = row.get("historical_trends") or {}
    sparklines = row.get("sparklines") or trends
    mentions_svg = _sparkline_svg(sparklines.get("mentions") or trends.get("mentions_7d", []))
    score_svg = _sparkline_svg(sparklines.get("score") or trends.get("score_7d", []))
    sources = "".join(_source_html(source) for source in row.get("top_sources", []))

    trend_blocks = ""
    if mentions_svg:
        trend_blocks += (
            f'<div class="mini-trend"><span>Mentions</span>{mentions_svg}</div>'
        )
    if score_svg:
        trend_blocks += f'<div class="mini-trend"><span>Score</span>{score_svg}</div>'

    return f"""
      <article class="card">
        <div class="card-header">
          <div class="identity">
            <span class="rank">#{row.get("rank", "-")}</span>
            <h2>{ticker}</h2>
          </div>
          <div class="score-block">
            <span class="score-label">Signal Score</span>
            <span class="score">{float(row.get("final_score", 0)):.0f}</span>
          </div>
        </div>

        <div class="headline-row">
          <span class="recommendation">{recommendation}</span>
          <span class="confidence-pill">{confidence} Confidence</span>
        </div>

        <p class="meta-line">{_meta_line(row)}</p>
        <div class="analyst-row">{_analyst_target_html(row)}</div>
        <p class="summary">{summary}</p>
        {_narrative_html(row)}

        <div class="signal-panel">{_signal_summary_html(row)}</div>
        {_key_metrics_html(row)}
        {f'<div class="mini-trends">{trend_blocks}</div>' if trend_blocks else ''}

        <details>
          <summary>More metrics & telemetry</summary>
          <div class="secondary-metrics">{_secondary_metrics_html(row)}</div>
        </details>
        <details>
          <summary>Score breakdown</summary>
          {_human_breakdown_html(row.get("score_breakdown") or {}, row)}
        </details>
        <details>
          <summary>Catalyst details</summary>
          {_catalyst_details_html(row)}
        </details>
        <details>
          <summary>Risk explanation</summary>
          <p>{escape(str(row.get("risk_explanation") or ""))}</p>
          <ul>{_list_html(row.get("risk_reasons") or [], "No risk reason details available.")}</ul>
        </details>
        <details>
          <summary>Historical trends</summary>
          {_trends_detail_html(row)}
        </details>
        <details>
          <summary>Reddit sources</summary>
          <ul>{sources or "<li>No source links available</li>"}</ul>
        </details>
      </article>
    """


def render_results_html(results: list[dict[str, Any]]) -> str:
    """Render ranked scanner results as a polished market-intelligence dashboard."""

    generated_at = results[0].get("generated_at") if results else "No scan results yet"
    cards = "".join(_card_html(row) for row in results) or '<div class="empty">No ranked tickers yet.</div>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reddit Alpha Scanner</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f4f6f8;
      --card: #ffffff;
      --text: #1b2430;
      --muted: #5f6b7a;
      --line: #e4e9ef;
      --accent: #0b57d0;
      --accent-soft: #e8f1ff;
      --up: #137333;
      --up-soft: #e6f4ea;
      --down: #b3261e;
      --down-soft: #fce8e6;
      --neutral: #5f6368;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f141b;
        --card: #171d25;
        --text: #e8edf3;
        --muted: #9aa7b5;
        --line: #2a3441;
        --accent: #6ea8fe;
        --accent-soft: #1a2a44;
        --up: #6dd58c;
        --up-soft: #173422;
        --down: #ff8a80;
        --down-soft: #3a1d1d;
        --neutral: #b0bac5;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 40px 20px 56px; }}
    header h1 {{ margin: 0 0 6px; font-size: clamp(28px, 4vw, 36px); font-weight: 650; letter-spacing: -0.02em; }}
    .meta, .disclaimer, .muted {{ color: var(--muted); font-size: 14px; }}
    .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 20px 0 10px; }}
    .toolbar a {{
      color: var(--text);
      text-decoration: none;
      padding: 8px 12px;
      border-radius: 8px;
      background: var(--card);
      border: 1px solid var(--line);
      font-size: 13px;
    }}
    .grid {{ display: grid; gap: 22px; }}
    .card {{
      background: var(--card);
      border-radius: 18px;
      padding: 24px 24px 18px;
      box-shadow: 0 8px 24px rgba(16, 24, 40, 0.04);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 14px;
    }}
    .identity {{ display: flex; align-items: baseline; gap: 12px; }}
    .rank {{ color: var(--muted); font-size: 14px; font-weight: 700; }}
    h2 {{ margin: 0; font-size: 30px; letter-spacing: 0.03em; font-weight: 700; }}
    .score-block {{ text-align: right; }}
    .score-label {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 2px; }}
    .score {{
      display: inline-block;
      font-size: 34px;
      font-weight: 700;
      color: var(--accent);
      line-height: 1;
    }}
    .headline-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .recommendation {{
      font-size: 15px;
      font-weight: 650;
      color: var(--accent);
      background: var(--accent-soft);
      border-radius: 999px;
      padding: 6px 12px;
    }}
    .confidence-pill {{
      font-size: 13px;
      color: var(--muted);
      font-weight: 600;
    }}
    .meta-line {{ margin: 0 0 10px; color: var(--muted); font-size: 14px; }}
    .analyst-row {{ margin-bottom: 14px; }}
    .analyst-target {{ font-size: 15px; font-weight: 650; }}
    .analyst-upside {{ color: var(--up); }}
    .analyst-downside {{ color: var(--down); }}
    .analyst-neutral {{ color: var(--neutral); }}
    .summary {{
      margin: 0 0 16px;
      font-size: 16px;
      line-height: 1.65;
      max-width: 72ch;
    }}
    .narrative-panel {{
      margin: 0 0 20px;
      padding: 14px 0 6px;
      border-top: 1px solid var(--line);
    }}
    .narrative-panel h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      font-weight: 650;
    }}
    .primary-narrative {{
      margin: 0 0 12px;
      font-size: 15px;
      line-height: 1.6;
      max-width: 72ch;
    }}
    .theme-columns {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      font-size: 14px;
    }}
    .theme-columns h4 {{
      margin: 0 0 6px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
    }}
    .theme-columns ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .signal-panel {{
      display: grid;
      gap: 8px;
      margin-bottom: 18px;
      padding: 14px 0 4px;
      border-top: 1px solid var(--line);
    }}
    .signal-row {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 14px;
    }}
    .signal-tier {{ font-weight: 650; }}
    .tier-strong {{ color: var(--up); }}
    .tier-moderate {{ color: var(--neutral); }}
    .tier-weak {{ color: var(--down); }}
    .tier-risk-high {{ color: var(--down); }}
    .tier-risk-low {{ color: var(--up); }}
    .key-metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 14px 18px;
      margin-bottom: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }}
    .metric-label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .metric-value {{ font-size: 15px; font-weight: 600; }}
    .mini-trends {{
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      margin-bottom: 8px;
      color: var(--muted);
    }}
    .mini-trend span {{
      display: block;
      font-size: 11px;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .sparkline {{ display: block; opacity: 0.8; }}
    details {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 600;
      color: var(--text);
      padding: 8px 0;
    }}
    .secondary-metrics {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    .readable-breakdown, .trend-series, .telemetry, .catalyst-details {{
      list-style: none;
      padding: 0;
      margin: 10px 0;
    }}
    .catalyst-details li {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 0;
      border-bottom: 1px solid var(--line);
    }}
    .readable-breakdown li, .trend-series li {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 0;
      border-bottom: 1px solid var(--line);
    }}
    .nested-details {{ margin-top: 10px; }}
    a {{ color: var(--accent); }}
    .empty {{
      padding: 28px;
      border-radius: 14px;
      color: var(--muted);
      background: var(--card);
      text-align: center;
    }}
    @media (max-width: 640px) {{
      .card-header {{ flex-direction: column; }}
      .score-block {{ text-align: left; }}
      h2 {{ font-size: 26px; }}
    }}
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
      <p class="disclaimer">Research/watchlist tool only. Not financial advice.</p>
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
