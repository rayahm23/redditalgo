"""Rule-based Reddit discussion narrative extraction per ticker."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

FALLBACK_NARRATIVE = "Discussion was too limited or scattered to identify a clear narrative."

THEME_RULES: tuple[dict[str, Any], ...] = (
    {
        "label": "AI datacenter demand",
        "polarity": "bullish",
        "keywords": (
            " ai ",
            "artificial intelligence",
            "datacenter",
            "data center",
            "gpu",
            "inference",
            "generative ai",
            "llm",
            "nvda",
        ),
    },
    {
        "label": "earnings optimism",
        "polarity": "bullish",
        "keywords": ("earnings beat", "earnings", "eps beat", "beat estimates", "record revenue"),
    },
    {
        "label": "guidance strength",
        "polarity": "bullish",
        "keywords": ("guidance raise", "raised guidance", "strong guidance", "guidance upgrade"),
    },
    {
        "label": "revenue growth",
        "polarity": "bullish",
        "keywords": ("revenue growth", "top-line growth", "sales growth", "growing revenue"),
    },
    {
        "label": "margin expansion",
        "polarity": "bullish",
        "keywords": ("margin expansion", "margin improvement", "higher margins"),
    },
    {
        "label": "free cash flow",
        "polarity": "bullish",
        "keywords": ("free cash flow", "fcf", "cash generation"),
    },
    {
        "label": "short squeeze",
        "polarity": "bullish",
        "keywords": ("short squeeze", "squeeze", "short interest", "covering shorts"),
    },
    {
        "label": "FDA / biotech catalyst",
        "polarity": "bullish",
        "keywords": ("fda approval", "fda", "phase 3", "clinical trial", "biotech", "drug approval"),
    },
    {
        "label": "acquisition / M&A",
        "polarity": "bullish",
        "keywords": ("acquisition", "merger", "buyout", "takeover", "m&a"),
    },
    {
        "label": "product launch",
        "polarity": "bullish",
        "keywords": ("product launch", "new product", "launch event", "rollout"),
    },
    {
        "label": "insider buying",
        "polarity": "bullish",
        "keywords": ("insider buying", "insider buy", "director buy"),
    },
    {
        "label": "technical breakout",
        "polarity": "bullish",
        "keywords": ("breakout", "above resistance", "new high", "52-week high"),
    },
    {
        "label": "analyst upgrade",
        "polarity": "bullish",
        "keywords": ("upgrade", "price target raised", "outperform", "overweight", "buy rating"),
    },
    {
        "label": "options activity",
        "polarity": "neutral",
        "keywords": ("unusual options", "options flow", "call volume", "put volume", "open interest"),
    },
    {
        "label": "macro / Fed",
        "polarity": "neutral",
        "keywords": ("fed", "interest rates", "cpi", "inflation", "macro", "treasury yields"),
    },
    {
        "label": "valuation concerns",
        "polarity": "bearish",
        "keywords": ("overvalued", "valuation", "too expensive", "priced in", "rich multiple"),
    },
    {
        "label": "NVDA competition",
        "polarity": "bearish",
        "keywords": ("nvda competition", "competition from nvda", "nvidia competition", "competitor"),
    },
    {
        "label": "dilution risk",
        "polarity": "bearish",
        "keywords": ("dilution", "secondary offering", "share offering", "atm offering"),
    },
    {
        "label": "bankruptcy risk",
        "polarity": "bearish",
        "keywords": ("bankruptcy", "going concern", "liquidity crisis", "default risk"),
    },
    {
        "label": "analyst downgrade",
        "polarity": "bearish",
        "keywords": ("downgrade", "price target cut", "underperform", "underweight", "sell rating"),
    },
    {
        "label": "insider selling",
        "polarity": "bearish",
        "keywords": ("insider selling", "insider sell", "executive sale"),
    },
    {
        "label": "regulatory / legal issue",
        "polarity": "bearish",
        "keywords": ("sec investigation", "lawsuit", "regulatory", "antitrust", "subpoena"),
    },
)


def _normalize_text(*parts: Any) -> str:
    return f" {' '.join(str(part or '') for part in parts).lower()} "


def _theme_hits(text: str) -> Counter[str]:
    hits: Counter[str] = Counter()
    for rule in THEME_RULES:
        if any(keyword in text for keyword in rule["keywords"]):
            hits[rule["label"]] += 1
    return hits


def _collect_source_text(source: dict[str, Any]) -> str:
    return _normalize_text(
        source.get("title"),
        source.get("selftext"),
        source.get("comments_excerpt"),
    )


def _themes_by_polarity(theme_counts: Counter[str]) -> dict[str, list[str]]:
    label_to_polarity = {rule["label"]: rule["polarity"] for rule in THEME_RULES}
    grouped: dict[str, list[str]] = {"bullish": [], "bearish": [], "neutral": []}
    for label, count in theme_counts.most_common():
        polarity = label_to_polarity.get(label, "neutral")
        grouped[polarity].append(label)
    return grouped


def _narrative_confidence(
    *,
    source_count: int,
    unique_subreddits: int,
    theme_hits: int,
    meme_share: float,
) -> tuple[str, float]:
    if source_count < 2 or theme_hits == 0:
        return "LOW", 0.25
    score = 0.25
    score += min(0.25, source_count / 12)
    score += min(0.2, unique_subreddits / 5 * 0.2)
    score += min(0.25, theme_hits / 6)
    if meme_share >= 0.5:
        score -= 0.2
    if unique_subreddits >= 2 and theme_hits >= 2:
        score += 0.1
    score = max(0.0, min(1.0, score))
    if score >= 0.65:
        return "HIGH", round(score, 4)
    if score >= 0.4:
        return "MEDIUM", round(score, 4)
    return "LOW", round(score, 4)


def _compose_primary_narrative(ticker: str, bullish: list[str], bearish: list[str], neutral: list[str]) -> str:
    if not bullish and not bearish and not neutral:
        return FALLBACK_NARRATIVE

    focus_parts: list[str] = []
    if bullish:
        focus_parts.append(", ".join(bullish[:3]))
    if bearish:
        focus_parts.append("concerns around " + ", ".join(bearish[:2]))
    focus = "; ".join(focus_parts)
    return f"Discussion focused on {ticker}'s {focus}."


def extract_ticker_narrative(
    ticker: str,
    sources: list[dict[str, Any]],
    *,
    post_types: list[str] | None = None,
    unique_subreddits: int = 0,
) -> dict[str, Any]:
    """Extract narrative themes and confidence from ticker-related Reddit text."""

    if not sources:
        return {
            "primary_narrative": FALLBACK_NARRATIVE,
            "bullish_themes": [],
            "bearish_themes": [],
            "neutral_themes": [],
            "narrative_confidence": "LOW",
            "narrative_confidence_score": 0.0,
            "narrative_keywords": [],
            "narrative_sources_count": 0,
        }

    theme_counts: Counter[str] = Counter()
    keywords: Counter[str] = Counter()

    for source in sources:
        text = _collect_source_text(source)
        theme_counts.update(_theme_hits(text))
        for token in re.findall(r"[a-z][a-z0-9]{3,}", text):
            if token in {"stock", "stocks", "reddit", "discussion", ticker.lower()}:
                continue
            keywords[token] += 1

    grouped = _themes_by_polarity(theme_counts)
    post_types = post_types or []
    meme_share = 0.0
    if post_types:
        meme_share = sum(1 for item in post_types if item in {"Meme", "YOLO"}) / len(post_types)

    label, confidence_score = _narrative_confidence(
        source_count=len(sources),
        unique_subreddits=unique_subreddits,
        theme_hits=sum(theme_counts.values()),
        meme_share=meme_share,
    )

    return {
        "primary_narrative": _compose_primary_narrative(
            ticker, grouped["bullish"], grouped["bearish"], grouped["neutral"]
        ),
        "bullish_themes": grouped["bullish"][:4],
        "bearish_themes": grouped["bearish"][:3],
        "neutral_themes": grouped["neutral"][:3],
        "narrative_confidence": label,
        "narrative_confidence_score": confidence_score,
        "narrative_keywords": [word for word, _ in keywords.most_common(8)],
        "narrative_sources_count": len(sources),
    }


def build_narrative_summary(
    ticker: str,
    narrative: dict[str, Any],
    *,
    attention_phrase: str,
    quality_phrase: str,
    market_phrase: str,
    street_phrase: str = "",
) -> str:
    """Combine narrative extraction with attention and market context."""

    primary = str(narrative.get("primary_narrative") or FALLBACK_NARRATIVE)
    if primary == FALLBACK_NARRATIVE:
        return (
            f"{ticker} mention activity {attention_phrase}, but {primary.lower()} "
            f"{quality_phrase} {market_phrase}{street_phrase}"
        ).strip()

    bullish = narrative.get("bullish_themes") or []
    focus = ", ".join(bullish[:3]) if bullish else "several overlapping themes"
    bearish = narrative.get("bearish_themes") or []
    caution = ""
    if bearish:
        caution = f" Bearish pushback included {', '.join(bearish[:2])}."
    return (
        f"{ticker} discussion {attention_phrase} as users focused on {focus}, {quality_phrase}. "
        f"{market_phrase}{street_phrase}{caution}"
    ).strip()
