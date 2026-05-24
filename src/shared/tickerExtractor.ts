import { EXCLUDED_TICKERS } from "./config.js";

const CASHTAG_PATTERN = /(?<![A-Za-z0-9_])\$([A-Za-z]{1,5})(?![A-Za-z])/g;
const PLAIN_TICKER_PATTERN = /(?<!\$)\b[A-Z]{2,5}\b/g;

export function normalizeTicker(candidate: string): string {
  return candidate.trim().replace(/^\$/, "").toUpperCase();
}

export function isProbableTicker(candidate: string, excluded = EXCLUDED_TICKERS): boolean {
  const ticker = normalizeTicker(candidate);
  return /^[A-Z]{1,5}$/.test(ticker) && !excluded.has(ticker);
}

export function extractTickersFromText(text: string | undefined | null): string[] {
  if (!text) {
    return [];
  }

  const tickers: string[] = [];
  for (const match of text.matchAll(CASHTAG_PATTERN)) {
    const ticker = normalizeTicker(match[1] ?? "");
    if (isProbableTicker(ticker)) {
      tickers.push(ticker);
    }
  }

  for (const match of text.matchAll(PLAIN_TICKER_PATTERN)) {
    const ticker = normalizeTicker(match[0]);
    if (isProbableTicker(ticker)) {
      tickers.push(ticker);
    }
  }

  return tickers;
}

export function extractTickersFromPost(
  title: string | undefined,
  selftext: string | undefined,
  comments: string[] = [],
): string[] {
  return [
    ...extractTickersFromText(title),
    ...extractTickersFromText(selftext),
    ...comments.flatMap((comment) => extractTickersFromText(comment)),
  ];
}
