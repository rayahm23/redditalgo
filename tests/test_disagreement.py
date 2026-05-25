from scanner.disagreement import analyze_disagreement, disagreement_summary_phrase
from scanner.scoring import TickerAggregate


def test_mixed_consensus_label():
    aggregate = TickerAggregate(ticker="AMD")
    aggregate.bullish_scores = [0.7, 0.6, 0.2]
    aggregate.bearish_scores = [0.2, 0.65, 0.7]
    aggregate.post_ids = {"a", "b", "c"}
    result = analyze_disagreement(aggregate)
    assert result["consensus_label"] == "Mixed / contested"
    assert result["bullish_evidence_count"] >= 1
    assert result["bearish_evidence_count"] >= 1


def test_disagreement_summary_phrase():
    text = disagreement_summary_phrase(
        consensus_label="Mixed / contested",
        bullish_themes=["AI GPU demand"],
        bearish_themes=["valuation concern"],
    )
    assert "mixed" in text.lower()
    assert "AI GPU" in text or "bullish" in text.lower()
