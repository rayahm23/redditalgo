"""Simple rule-based Reddit post classification."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

POST_TYPE_WEIGHTS = {
    "DD": 1.5,
    "News": 1.3,
    "Earnings": 1.25,
    "Options": 1.2,
    "YOLO": 0.8,
    "Meme": 0.4,
    "Question": 0.3,
    "Other": 1.0,
}

KEYWORDS = {
    "DD": (" dd ", "due diligence", "deep dive", "analysis", "thesis", "valuation", "fundamental"),
    "News": ("news", "breaking", "reported", "announces", "announced", "sec filing", "approval", "partnership"),
    "Earnings": ("earnings", "guidance", "revenue", "eps", "quarter", "q1", "q2", "q3", "q4"),
    "Options": ("calls", "puts", "options", "leaps", "strike", "expiry", "expiration", "itm", "otm"),
    "YOLO": ("yolo", "all in", "all-in", "life savings", "0dte", "fd "),
    "Meme": ("meme", "rocket", "moon", "stonk", "diamond hands", "tendies", "apes", "🚀", "🌕"),
    "Question": ("?", "what do you think", "thoughts", "should i", "anyone buying", "why is"),
}

ORDER = ("DD", "News", "Earnings", "Options", "YOLO", "Meme", "Question")


def _normalize(text: str) -> str:
    return f" {text.lower()} "


def classify_post(title: str | None, selftext: str | None = None, comments: Iterable[str] | None = None) -> str:
    """Classify a Reddit post into one explainable category using keyword rules."""

    text = _normalize(" ".join([title or "", selftext or "", " ".join(comments or [])]))
    for post_type in ORDER:
        if any(keyword in text for keyword in KEYWORDS[post_type]):
            return post_type
    return "Other"


def post_type_weight(post_type: str) -> float:
    return POST_TYPE_WEIGHTS.get(post_type, POST_TYPE_WEIGHTS["Other"])


def dominant_post_type(post_types: Iterable[str]) -> str:
    counts = Counter(post_types)
    if not counts:
        return "Other"
    return counts.most_common(1)[0][0]
