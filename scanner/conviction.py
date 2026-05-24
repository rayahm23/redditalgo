"""Rule-based conviction phrase scoring."""

from __future__ import annotations

from typing import Iterable

BULLISH_PHRASES = (
    "buying calls",
    "loaded",
    "all in",
    "all-in",
    "adding",
    "holding",
    "shares",
    "leaps",
    "squeeze",
    "short interest",
    "earnings",
    "guidance",
    "price target",
    " pt ",
    "breakout",
    "unusual volume",
)

BEARISH_PHRASES = (
    "puts",
    "shorting",
    "rug pull",
    "overvalued",
    "dilution",
    "bankruptcy",
    "selloff",
    "downside",
)


def _text_blob(title: str | None, selftext: str | None = None, comments: Iterable[str] | None = None) -> str:
    return f" {' '.join([title or '', selftext or '', ' '.join(comments or [])]).lower()} "


def _phrase_score(text: str, phrases: tuple[str, ...]) -> float:
    matches = sum(1 for phrase in phrases if phrase in text)
    return min(1.0, matches / 4)


def conviction_scores(title: str | None, selftext: str | None = None, comments: Iterable[str] | None = None) -> dict[str, float]:
    """Return bullish, bearish, and net conviction scores from 0 to 1."""

    text = _text_blob(title, selftext, comments)
    bullish = _phrase_score(text, BULLISH_PHRASES)
    bearish = _phrase_score(text, BEARISH_PHRASES)
    net = max(0.0, min(1.0, 0.5 + (bullish - bearish) / 2))
    return {
        "bullish_conviction_score": round(bullish, 4),
        "bearish_conviction_score": round(bearish, 4),
        "net_conviction_score": round(net, 4),
    }
