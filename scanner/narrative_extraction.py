"""Rule-based Reddit discussion narrative extraction per ticker."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

FALLBACK_NARRATIVE = "Discussion was too limited or scattered to identify a clear narrative."

CUSTOM_STOPWORDS = frozenset({
    "have", "this", "that", "what", "also", "would", "could", "should", "really",
    "think", "going", "still", "even", "just", "much", "very", "make", "made",
    "many", "some", "more", "well", "good", "great", "thing", "things", "stock",
    "company", "shares", "market", "today", "tomorrow", "people", "guys", "lol",
    "lmao", "bro", "yeah", "with", "from", "they", "them", "your", "about", "into",
    "been", "were", "will", "when", "than", "then", "here", "there", "where",
    "like", "know", "want", "need", "said", "says", "does", "dont", "doesnt",
    "been", "being", "only", "over", "under", "after", "before", "while", "because",
    "reddit", "post", "posts", "comment", "comments", "thread", "threads",
})

KNOWN_FINANCE_PHRASES: tuple[str, ...] = (
    "free cash flow",
    "margin expansion",
    "earnings guidance",
    "ai demand",
    "data center",
    "data center growth",
    "short squeeze",
    "short interest",
    "market share",
    "revenue growth",
    "analyst upgrade",
    "analyst downgrade",
    "operating leverage",
    "price target",
    "enterprise demand",
    "gross margin",
    "multiple expansion",
    "relative strength",
    "earnings beat",
    "guidance raise",
    "earnings optimism",
    "enterprise ai",
    "ai datacenter",
    "ai growth",
    "cash flow",
    "operating margin",
    "top line growth",
    "fda approval",
    "insider buying",
    "insider selling",
    "technical breakout",
    "dilution risk",
    "bankruptcy risk",
)

FINANCE_PHRASE_BOOST = 3

PHRASE_CLUSTERS: tuple[dict[str, Any], ...] = (
    {
        "canonical": "AI/datacenter demand",
        "patterns": (
            "ai demand", "ai growth", "ai datacenter", "enterprise ai",
            "data center", "data center growth", "datacenter", "gpu demand",
            "generative ai", "inference demand",
        ),
    },
    {
        "canonical": "Earnings optimism",
        "patterns": (
            "earnings beat", "guidance raise", "strong earnings", "earnings guidance",
            "earnings optimism", "eps beat", "beat estimates", "record revenue",
        ),
    },
    {
        "canonical": "Margin / cash flow strength",
        "patterns": (
            "margin expansion", "free cash flow", "cash flow", "gross margin",
            "operating leverage", "operating margin",
        ),
    },
    {
        "canonical": "Short squeeze / interest",
        "patterns": (
            "short squeeze", "short interest", "covering shorts", "squeeze setup",
        ),
    },
    {
        "canonical": "Valuation / multiple debate",
        "patterns": (
            "valuation concerns", "multiple expansion", "overvalued", "rich multiple",
            "priced in", "too expensive",
        ),
    },
    {
        "canonical": "Analyst / price target",
        "patterns": (
            "analyst upgrade", "analyst downgrade", "price target", "target raised",
            "target cut", "outperform", "underperform",
        ),
    },
    {
        "canonical": "Revenue / market share",
        "patterns": (
            "revenue growth", "market share", "top line growth", "sales growth",
            "enterprise demand",
        ),
    },
)

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
            "ai demand",
            "enterprise ai",
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
        "keywords": ("guidance raise", "raised guidance", "strong guidance", "guidance upgrade", "earnings guidance"),
    },
    {
        "label": "revenue growth",
        "polarity": "bullish",
        "keywords": ("revenue growth", "top-line growth", "sales growth", "growing revenue", "market share"),
    },
    {
        "label": "margin expansion",
        "polarity": "bullish",
        "keywords": ("margin expansion", "margin improvement", "higher margins", "gross margin"),
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
        "keywords": ("breakout", "above resistance", "new high", "52-week high", "relative strength"),
    },
    {
        "label": "analyst upgrade",
        "polarity": "bullish",
        "keywords": ("upgrade", "price target raised", "outperform", "overweight", "buy rating", "analyst upgrade"),
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
        "keywords": ("overvalued", "valuation", "too expensive", "priced in", "rich multiple", "multiple expansion"),
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
        "keywords": ("downgrade", "price target cut", "underperform", "underweight", "sell rating", "analyst downgrade"),
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

_TOKEN_RE = re.compile(r"[a-z][a-z0-9'-]{1,}")


def _normalize_text(*parts: Any) -> str:
    cleaned = f" {' '.join(str(part or '') for part in parts).lower()} "
    cleaned = re.sub(r"[^a-z0-9$%'\s/-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned)


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text):
        token = token.strip("'")
        if len(token) < 2 or token in CUSTOM_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _cluster_phrase(phrase: str) -> str:
    normalized = phrase.strip().lower()
    for cluster in PHRASE_CLUSTERS:
        for pattern in cluster["patterns"]:
            if pattern in normalized or normalized in pattern:
                return str(cluster["canonical"])
    return phrase.strip().title() if len(phrase) > 3 else phrase


def _extract_known_finance_phrases(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for phrase in KNOWN_FINANCE_PHRASES:
        occurrences = text.count(phrase)
        if occurrences:
            counts[_cluster_phrase(phrase)] += occurrences * FINANCE_PHRASE_BOOST
    return counts


def _extract_ngrams(tokens: list[str], n: int) -> Counter[str]:
    counts: Counter[str] = Counter()
    if len(tokens) < n:
        return counts
    for index in range(len(tokens) - n + 1):
        window = tokens[index : index + n]
        if any(token in CUSTOM_STOPWORDS for token in window):
            continue
        phrase = " ".join(window)
        if all(len(part) <= 2 for part in window):
            continue
        counts[phrase] += 1 + (0.5 if n == 3 else 0.0)
    return counts


def extract_finance_phrases(text: str, *, ticker: str = "") -> list[str]:
    """Extract ranked finance-aware phrases (bigrams/trigrams + known phrases)."""

    normalized = _normalize_text(text)
    ticker_lower = ticker.lower()
    phrase_counts: Counter[str] = Counter()
    phrase_counts.update(_extract_known_finance_phrases(normalized))

    tokens = [token for token in _tokenize(normalized) if token != ticker_lower]
    for n in (3, 2):
        for phrase, count in _extract_ngrams(tokens, n).items():
            if any(stop in phrase.split() for stop in CUSTOM_STOPWORDS):
                continue
            if phrase in KNOWN_FINANCE_PHRASES:
                phrase_counts[_cluster_phrase(phrase)] += count * FINANCE_PHRASE_BOOST
            else:
                phrase_counts[_cluster_phrase(phrase)] += count

    ranked = [
        phrase
        for phrase, _ in phrase_counts.most_common()
        if phrase and not _is_low_value_phrase(phrase)
    ]
    return ranked[:8]


def _is_low_value_phrase(phrase: str) -> bool:
    words = phrase.lower().split()
    if not words:
        return True
    if len(words) == 1 and words[0] in CUSTOM_STOPWORDS:
        return True
    if all(word in CUSTOM_STOPWORDS for word in words):
        return True
    return False


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
    for label, _count in theme_counts.most_common():
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
    phrase_counts: Counter[str] = Counter()
    combined_text = ""

    for source in sources:
        text = _collect_source_text(source)
        combined_text += text
        theme_counts.update(_theme_hits(text))
        for phrase in extract_finance_phrases(text, ticker=ticker):
            phrase_counts[phrase] += 1

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

    keywords = [phrase for phrase, _ in phrase_counts.most_common(8) if not _is_low_value_phrase(phrase)]
    if not keywords:
        keywords = extract_finance_phrases(combined_text, ticker=ticker)[:6]

    return {
        "primary_narrative": _compose_primary_narrative(
            ticker, grouped["bullish"], grouped["bearish"], grouped["neutral"]
        ),
        "bullish_themes": grouped["bullish"][:4],
        "bearish_themes": grouped["bearish"][:3],
        "neutral_themes": grouped["neutral"][:3],
        "narrative_confidence": label,
        "narrative_confidence_score": confidence_score,
        "narrative_keywords": keywords,
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
