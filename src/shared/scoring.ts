import type { MarketData, RankedTicker, SourcePost, TickerAggregate } from "./types.js";
import { extractTickersFromPost } from "./tickerExtractor.js";
import { scorePostSentiment } from "./sentiment.js";

export function aggregatePosts(posts: SourcePost[]): Map<string, TickerAggregate> {
  const aggregates = new Map<string, TickerAggregate>();

  for (const post of posts) {
    const mentions = extractTickersFromPost(post.title, post.selftext, post.topComments);
    if (mentions.length === 0) {
      continue;
    }

    const sentiment = scorePostSentiment(post.title, post.selftext, post.topComments);
    const counts = new Map<string, number>();
    for (const ticker of mentions) {
      counts.set(ticker, (counts.get(ticker) ?? 0) + 1);
    }

    for (const [ticker, count] of counts) {
      const aggregate = aggregates.get(ticker) ?? {
        ticker,
        mentionCount: 0,
        postIds: new Set<string>(),
        totalUpvotes: 0,
        commentVolume: 0,
        sentimentScores: [],
        sources: [],
      };

      aggregate.mentionCount += count;
      aggregate.postIds.add(post.id);
      aggregate.totalUpvotes += post.score;
      aggregate.commentVolume += post.numComments;
      aggregate.sentimentScores.push(sentiment);
      aggregate.sources.push({
        subreddit: post.subreddit,
        title: post.title,
        permalink: post.permalink,
        score: post.score,
      });
      aggregates.set(ticker, aggregate);
    }
  }

  return aggregates;
}

export function averageSentiment(aggregate: TickerAggregate): number {
  if (aggregate.sentimentScores.length === 0) {
    return 0;
  }
  const average = aggregate.sentimentScores.reduce((sum, score) => sum + score, 0) / aggregate.sentimentScores.length;
  return Number(average.toFixed(4));
}

export function determineRiskFlag(marketData: MarketData): "low" | "medium" | "high" {
  if (!marketData.valid) {
    return "high";
  }

  if (
    (marketData.latestPrice !== undefined && marketData.latestPrice < 5) ||
    (marketData.avgVolume !== undefined && marketData.avgVolume < 500_000) ||
    (marketData.marketCap !== undefined && marketData.marketCap < 300_000_000)
  ) {
    return "high";
  }

  if (
    marketData.latestPrice !== undefined &&
    marketData.latestPrice >= 5 &&
    marketData.avgVolume !== undefined &&
    marketData.avgVolume >= 2_000_000 &&
    marketData.marketCap !== undefined &&
    marketData.marketCap >= 10_000_000_000
  ) {
    return "low";
  }

  return "medium";
}

export function calculateFinalScore(aggregate: TickerAggregate, marketData: MarketData): number {
  const attentionScore = Math.log1p(aggregate.mentionCount) * 12 + aggregate.postIds.size * 4;
  const engagementScore = Math.log1p(Math.max(aggregate.totalUpvotes, 0)) * 6 +
    Math.log1p(Math.max(aggregate.commentVolume, 0)) * 4;
  const sentimentScore = ((averageSentiment(aggregate) + 1) / 2) * 22;
  const validityBonus = marketData.valid ? 8 : 0;
  const riskPenalty = { high: 10, medium: 4, low: 0 }[determineRiskFlag(marketData)];
  const rawScore = attentionScore + engagementScore + sentimentScore + validityBonus;
  return Number(Math.max(0, Math.min(100, rawScore) - riskPenalty).toFixed(2));
}

function buildSummary(aggregate: TickerAggregate, riskFlag: "low" | "medium" | "high"): string {
  const sentiment = averageSentiment(aggregate);
  const sentimentLabel = sentiment >= 0.25 ? "positive sentiment" : sentiment <= -0.25 ? "negative sentiment" : "mixed sentiment";
  const attentionLabel = aggregate.postIds.size >= 5 || aggregate.mentionCount >= 10 ? "High Reddit attention" : "Emerging Reddit attention";
  const riskLabel = riskFlag === "high" ? "high-risk market profile" : `${riskFlag}-risk market profile`;
  return `${attentionLabel} with ${sentimentLabel} and a ${riskLabel}.`;
}

export function rankTickers(
  aggregates: Map<string, TickerAggregate>,
  marketDataByTicker: Map<string, MarketData>,
  generatedAt: string,
  limit: number,
): RankedTicker[] {
  const rows: Omit<RankedTicker, "rank">[] = [];

  for (const [ticker, aggregate] of aggregates) {
    const marketData = marketDataByTicker.get(ticker) ?? { valid: false };
    if (!marketData.valid) {
      continue;
    }

    const riskFlag = determineRiskFlag(marketData);
    const topSources = [...aggregate.sources]
      .sort((left, right) => right.score - left.score)
      .slice(0, 3)
      .map(({ subreddit, title, permalink }) => ({ subreddit, title, permalink }));

    rows.push({
      ticker,
      final_score: calculateFinalScore(aggregate, marketData),
      mention_count: aggregate.mentionCount,
      unique_posts: aggregate.postIds.size,
      avg_sentiment: averageSentiment(aggregate),
      total_upvotes: aggregate.totalUpvotes,
      comment_volume: aggregate.commentVolume,
      latest_price: marketData.latestPrice ?? null,
      market_cap: marketData.marketCap ?? null,
      avg_volume: marketData.avgVolume ?? null,
      risk_flag: riskFlag,
      summary: buildSummary(aggregate, riskFlag),
      top_sources: topSources,
      generated_at: generatedAt,
    });
  }

  return rows
    .sort((left, right) => right.final_score - left.final_score)
    .slice(0, limit)
    .map((row, index) => ({ rank: index + 1, ...row }));
}
