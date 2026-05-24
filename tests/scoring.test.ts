import { describe, expect, it } from "vitest";
import type { MarketData, SourcePost, TickerAggregate } from "../src/shared/types.js";
import { aggregatePosts, calculateFinalScore, determineRiskFlag, rankTickers } from "../src/shared/scoring.js";

function aggregate(overrides: Partial<TickerAggregate> = {}): TickerAggregate {
  return {
    ticker: "TSLA",
    mentionCount: 10,
    postIds: new Set(["a", "b", "c"]),
    totalUpvotes: 1_000,
    commentVolume: 200,
    sentimentScores: [0.5, 0.7],
    sources: [{ subreddit: "stocks", title: "TSLA", permalink: "https://reddit.com/x", score: 100 }],
    ...overrides,
  };
}

describe("scoring", () => {
  it("aggregates mentions and unique posts", () => {
    const posts: SourcePost[] = [
      {
        id: "a",
        subreddit: "wallstreetbets",
        title: "TSLA TSLA breakout",
        selftext: "I like $tsla",
        score: 100,
        numComments: 20,
        createdUtc: 0,
        permalink: "https://reddit.com/a",
        topComments: ["TSLA looks strong"],
      },
      {
        id: "b",
        subreddit: "stocks",
        title: "NVDA and TSLA watchlist",
        selftext: "",
        score: 50,
        numComments: 5,
        createdUtc: 0,
        permalink: "https://reddit.com/b",
        topComments: [],
      },
    ];

    const aggregates = aggregatePosts(posts);
    expect(aggregates.get("TSLA")?.mentionCount).toBe(5);
    expect(aggregates.get("TSLA")?.postIds.size).toBe(2);
    expect(aggregates.get("TSLA")?.totalUpvotes).toBe(150);
    expect(aggregates.get("NVDA")?.mentionCount).toBe(1);
  });

  it("sets market risk flags", () => {
    expect(determineRiskFlag({ valid: false })).toBe("high");
    expect(determineRiskFlag({ valid: true, latestPrice: 2.5, avgVolume: 5_000_000, marketCap: 2_000_000_000 })).toBe("high");
    expect(determineRiskFlag({ valid: true, latestPrice: 50, avgVolume: 3_000_000, marketCap: 15_000_000_000 })).toBe("low");
    expect(determineRiskFlag({ valid: true, latestPrice: 20, avgVolume: 800_000, marketCap: 2_000_000_000 })).toBe("medium");
  });

  it("keeps risk visible when attention saturates the score cap", () => {
    const lowRisk: MarketData = { valid: true, latestPrice: 200, avgVolume: 50_000_000, marketCap: 500_000_000_000 };
    const highRisk: MarketData = { valid: true, latestPrice: 2, avgVolume: 100_000, marketCap: 50_000_000 };

    expect(calculateFinalScore(aggregate(), lowRisk)).toBeGreaterThan(calculateFinalScore(aggregate(), highRisk));
  });

  it("filters invalid market data and ranks valid tickers", () => {
    const validAggregate = aggregate({ mentionCount: 3, postIds: new Set(["post-1"]), totalUpvotes: 100, commentVolume: 10 });
    const invalidAggregate = aggregate({ ticker: "FAKE", mentionCount: 20, postIds: new Set(["post-2"]) });
    const results = rankTickers(
      new Map([
        ["TSLA", validAggregate],
        ["FAKE", invalidAggregate],
      ]),
      new Map([
        ["TSLA", { valid: true, latestPrice: 200, avgVolume: 10_000_000, marketCap: 700_000_000_000 }],
        ["FAKE", { valid: false }],
      ]),
      "2026-05-24T00:00:00.000Z",
      15,
    );

    expect(results.map((row) => row.ticker)).toEqual(["TSLA"]);
    expect(results[0]?.rank).toBe(1);
    expect(results[0]?.generated_at).toBe("2026-05-24T00:00:00.000Z");
  });
});
