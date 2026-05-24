export type SourcePost = {
  id: string;
  subreddit: string;
  title: string;
  selftext: string;
  score: number;
  numComments: number;
  createdUtc: number;
  permalink: string;
  topComments: string[];
};

export type MarketData = {
  valid: boolean;
  latestPrice?: number;
  avgVolume?: number;
  marketCap?: number;
};

export type TickerAggregate = {
  ticker: string;
  mentionCount: number;
  postIds: Set<string>;
  totalUpvotes: number;
  commentVolume: number;
  sentimentScores: number[];
  sources: Array<{
    subreddit: string;
    title: string;
    permalink: string;
    score: number;
  }>;
};

export type RankedTicker = {
  rank: number;
  ticker: string;
  final_score: number;
  mention_count: number;
  unique_posts: number;
  avg_sentiment: number;
  total_upvotes: number;
  comment_volume: number;
  latest_price: number | null;
  market_cap: number | null;
  avg_volume: number | null;
  risk_flag: "low" | "medium" | "high";
  summary: string;
  top_sources: Array<{
    subreddit: string;
    title: string;
    permalink: string;
  }>;
  generated_at: string;
};

export type ScanPayload = {
  generated_at: string;
  subreddits: string[];
  results: RankedTicker[];
};
