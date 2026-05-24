"""Sentiment scoring using VADER."""

from __future__ import annotations

from collections.abc import Iterable

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_ANALYZER = SentimentIntensityAnalyzer()


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def score_text(text: str | None) -> float:
    """Return VADER compound sentiment for a single text blob."""

    if not text or not text.strip():
        return 0.0
    return float(_ANALYZER.polarity_scores(text)["compound"])


def score_post_sentiment(
    title: str | None, selftext: str | None, comments: Iterable[str] | None = None
) -> float:
    """Score a post from -1 to 1, weighting title/body above comments."""

    weighted_scores: list[tuple[float, float]] = []

    if title and title.strip():
        weighted_scores.append((score_text(title), 0.45))
    if selftext and selftext.strip():
        weighted_scores.append((score_text(selftext), 0.35))

    comment_values = [score_text(comment) for comment in comments or [] if comment]
    if comment_values:
        weighted_scores.append((sum(comment_values) / len(comment_values), 0.20))

    if not weighted_scores:
        return 0.0

    total_weight = sum(weight for _, weight in weighted_scores)
    weighted_average = sum(score * weight for score, weight in weighted_scores) / total_weight
    return round(_clamp(weighted_average), 4)
