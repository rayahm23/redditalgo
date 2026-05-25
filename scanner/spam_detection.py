"""Duplicate and spam-pattern detection for Reddit ticker discussion."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_WORD_RE = re.compile(r"[a-z]{3,}")
_STOP = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "have", "stock", "like",
    "just", "about", "into", "your", "what", "when", "will", "been", "they", "them",
})


def _source_text(source: dict[str, Any]) -> str:
    return " ".join(
        str(source.get(key) or "")
        for key in ("title", "selftext", "comments_excerpt")
    ).lower()


def _fingerprint(text: str) -> set[str]:
    return {token for token in _WORD_RE.findall(text) if token not in _STOP}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def duplicate_content_score(sources: list[dict[str, Any]]) -> float:
    """Score 0-1 for near-duplicate wording across sources (copy-paste clusters)."""

    fingerprints = [_fingerprint(_source_text(source)) for source in sources if _source_text(source)]
    if len(fingerprints) < 2:
        return 0.0
    max_similarity = 0.0
    for index in range(len(fingerprints)):
        for other in range(index + 1, len(fingerprints)):
            max_similarity = max(max_similarity, _jaccard(fingerprints[index], fingerprints[other]))
    return round(max_similarity, 4)


def repeated_ticker_score(aggregate: Any) -> float:
    """Score repeated ticker spam inside the same post/comment."""

    repeated = max(0, int(getattr(aggregate, "max_repeated_mentions", 0) or 0) - 2)
    return round(min(1.0, repeated / 8), 4)


def spam_cluster_score(sources: list[dict[str, Any]], duplicate_score: float) -> float:
    """Score coordinated similar posts pushing the same wording."""

    if len(sources) < 3:
        return round(duplicate_score * 0.5, 4) if duplicate_score >= 0.75 else 0.0
    high_pairs = 0
    fingerprints = [_fingerprint(_source_text(source)) for source in sources]
    for index in range(len(fingerprints)):
        for other in range(index + 1, len(fingerprints)):
            if _jaccard(fingerprints[index], fingerprints[other]) >= 0.72:
                high_pairs += 1
    cluster = min(1.0, high_pairs / max(len(sources) - 1, 1))
    return round(max(cluster, duplicate_score * 0.85), 4)


def author_promotion_score(aggregate: Any) -> float:
    """Score when the same author repeatedly pushes the ticker, if author metadata exists."""

    authors = [str(source.get("author") or "").strip() for source in getattr(aggregate, "sources", [])]
    authors = [author for author in authors if author and author.lower() != "[deleted]"]
    if not authors:
        return 0.0
    counts = Counter(authors)
    top = counts.most_common(1)[0][1]
    if top <= 1:
        return 0.0
    return round(min(1.0, (top - 1) / max(len(authors), 2)), 4)


def emoji_hype_score(aggregate: Any) -> float:
    """Score rocket/moon emoji language density."""

    return round(min(1.0, int(getattr(aggregate, "hype_count", 0) or 0) / 10), 4)


def analyze_spam(aggregate: Any) -> dict[str, Any]:
    """Return spam/duplicate metrics and a human-readable explanation."""

    sources = list(getattr(aggregate, "sources", []) or [])
    duplicate = duplicate_content_score(sources)
    repeated = repeated_ticker_score(aggregate)
    cluster = spam_cluster_score(sources, duplicate)
    author_push = author_promotion_score(aggregate)
    emoji = emoji_hype_score(aggregate)

    reasons: list[str] = []
    if duplicate >= 0.75:
        reasons.append("Multiple posts use near-identical wording.")
    if cluster >= 0.65:
        reasons.append("Similar posts cluster like coordinated copy-paste promotion.")
    if repeated >= 0.45:
        reasons.append("Ticker is repeated excessively inside the same post/comment.")
    if author_push >= 0.5:
        reasons.append("The same author appears to be pushing this ticker repeatedly.")
    if emoji >= 0.5:
        reasons.append("Heavy rocket/moon emoji language detected.")

    combined = max(duplicate * 0.35, cluster * 0.30, repeated * 0.20, author_push * 0.10, emoji * 0.15)
    if cluster >= 0.7 and duplicate >= 0.7:
        combined = min(1.0, combined + 0.15)

    return {
        "duplicate_content_score": duplicate,
        "spam_cluster_score": round(cluster, 4),
        "repeated_ticker_score": repeated,
        "author_promotion_score": round(author_push, 4),
        "emoji_hype_score": emoji,
        "spam_risk_explanation": " ".join(reasons) if reasons else "No major duplicate/spam cluster detected.",
        "spam_composite_score": round(min(1.0, combined), 4),
    }
