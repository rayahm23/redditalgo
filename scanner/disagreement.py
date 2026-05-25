"""Bullish vs bearish disagreement and consensus labeling."""

from __future__ import annotations

from typing import Any

def _evidence_count(scores: list[float], threshold: float = 0.52) -> int:
    return sum(1 for score in scores if score >= threshold)


def analyze_disagreement(aggregate: Any) -> dict[str, Any]:
    """Measure whether discussion leans bullish, bearish, mixed, or unclear."""

    bullish_count = _evidence_count(list(getattr(aggregate, "bullish_scores", []) or []))
    bearish_count = _evidence_count(list(getattr(aggregate, "bearish_scores", []) or []))
    total_posts = max(int(getattr(aggregate, "unique_posts", 0) or 0), 1)
    sentiment = float(getattr(aggregate, "avg_sentiment", 0) or 0)

    bullish_ratio = bullish_count / total_posts
    bearish_ratio = bearish_count / total_posts
    gap = abs(bullish_ratio - bearish_ratio)

    if bullish_count == 0 and bearish_count == 0:
        if sentiment >= 0.2:
            label = "Leaning bullish"
        elif sentiment <= -0.2:
            label = "Leaning bearish"
        else:
            label = "Unclear"
        disagreement = 0.55
    elif bullish_count >= 2 and bearish_count == 0 and sentiment >= 0.1:
        label = "Strong bullish consensus"
        disagreement = round(max(0.0, 1.0 - gap - bearish_ratio), 4)
    elif bearish_count >= 2 and bullish_count == 0 and sentiment <= -0.05:
        label = "Strong bearish consensus"
        disagreement = round(max(0.0, 1.0 - gap - bullish_ratio), 4)
    elif bullish_ratio >= 0.45 and bearish_ratio <= 0.2:
        label = "Leaning bullish"
        disagreement = round(min(1.0, bearish_ratio + 0.25), 4)
    elif bearish_ratio >= 0.45 and bullish_ratio <= 0.2:
        label = "Leaning bearish"
        disagreement = round(min(1.0, bullish_ratio + 0.25), 4)
    elif bullish_count > 0 and bearish_count > 0:
        label = "Mixed / contested"
        disagreement = round(min(1.0, 0.35 + min(bullish_ratio, bearish_ratio)), 4)
    else:
        label = "Unclear"
        disagreement = 0.5

    return {
        "bullish_evidence_count": bullish_count,
        "bearish_evidence_count": bearish_count,
        "disagreement_score": disagreement,
        "consensus_label": label,
    }


def disagreement_summary_phrase(
    *,
    consensus_label: str,
    bullish_claims: list[Any] | None = None,
    bearish_claims: list[Any] | None = None,
    bullish_themes: list[str] | None = None,
    bearish_themes: list[str] | None = None,
) -> str:
    """Build a short mixed-discussion sentence for summaries."""

    if consensus_label != "Mixed / contested":
        return ""

    def labels(items: list[Any] | None, fallback: list[str] | None) -> list[str]:
        result: list[str] = []
        for item in items or []:
            if isinstance(item, dict):
                result.append(str(item.get("short_label") or item.get("claim_text") or ""))
            else:
                result.append(str(item))
        if not result and fallback:
            result = [str(theme) for theme in fallback]
        return [label for label in result if label][:2]

    bull = labels(bullish_claims, bullish_themes)
    bear = labels(bearish_claims, bearish_themes)
    if not bull and not bear:
        return "Discussion is mixed with competing bullish and bearish takes."
    bull_text = ", ".join(bull) if bull else "bullish catalysts"
    bear_text = ", ".join(bear) if bear else "valuation and risk concerns"
    return (
        f"Discussion is mixed: bullish users point to {bull_text}, "
        f"while bearish users focus on {bear_text}."
    )
