import { SentimentIntensityAnalyzer } from "vader-sentiment";

function clamp(value: number, lower = -1, upper = 1): number {
  return Math.max(lower, Math.min(upper, value));
}

export function scoreText(text: string | undefined | null): number {
  if (!text?.trim()) {
    return 0;
  }
  return SentimentIntensityAnalyzer.polarity_scores(text).compound;
}

export function scorePostSentiment(
  title: string | undefined,
  selftext: string | undefined,
  comments: string[] = [],
): number {
  const weighted: Array<[number, number]> = [];

  if (title?.trim()) {
    weighted.push([scoreText(title), 0.45]);
  }
  if (selftext?.trim()) {
    weighted.push([scoreText(selftext), 0.35]);
  }

  const commentScores = comments.filter(Boolean).map((comment) => scoreText(comment));
  if (commentScores.length > 0) {
    const average = commentScores.reduce((sum, score) => sum + score, 0) / commentScores.length;
    weighted.push([average, 0.2]);
  }

  if (weighted.length === 0) {
    return 0;
  }

  const totalWeight = weighted.reduce((sum, [, weight]) => sum + weight, 0);
  const score = weighted.reduce((sum, [value, weight]) => sum + value * weight, 0) / totalWeight;
  return Number(clamp(score).toFixed(4));
}
