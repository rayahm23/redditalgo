export const SUBREDDITS = [
  "wallstreetbets",
  "stocks",
  "investing",
  "pennystocks",
  "options",
  "shortsqueeze",
] as const;

export const EXCLUDED_TICKERS = new Set([
  "DD",
  "YOLO",
  "CEO",
  "CFO",
  "SEC",
  "USA",
  "USD",
  "AI",
  "GDP",
  "CPI",
  "ETF",
  "IPO",
  "ATH",
  "FOMO",
  "IMO",
  "LOL",
  "OP",
  "THE",
  "FOR",
  "AND",
  "ARE",
  "YOU",
  "NOT",
]);

export const POSTS_PER_LISTING = 8;
export const TOP_COMMENTS_PER_POST = 3;
export const MAX_MARKET_LOOKUPS = 25;
export const TOP_RESULT_LIMIT = 15;
export const SCAN_RESULT_KEY = "reddit-alpha-scanner:latest";
