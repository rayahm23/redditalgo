import type { MarketData } from "./types.js";

type YahooQuote = {
  symbol?: string;
  regularMarketPrice?: number;
  marketCap?: number;
  averageDailyVolume3Month?: number;
  averageDailyVolume10Day?: number;
  regularMarketVolume?: number;
};

type YahooQuoteResponse = {
  quoteResponse?: {
    result?: YahooQuote[];
  };
};

function positiveNumber(value: unknown): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : undefined;
}

export async function getMarketDataForTickers(
  tickers: string[],
  fetchImpl: typeof fetch = fetch,
): Promise<Map<string, MarketData>> {
  const uniqueTickers = [...new Set(tickers.map((ticker) => ticker.toUpperCase()))];
  const marketData = new Map<string, MarketData>();

  if (uniqueTickers.length === 0) {
    return marketData;
  }

  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(
    uniqueTickers.join(","),
  )}`;

  try {
    const response = await fetchImpl(url);
    if (!response.ok) {
      throw new Error(`Yahoo quote request failed: ${response.status}`);
    }
    const payload = (await response.json()) as YahooQuoteResponse;
    for (const quote of payload.quoteResponse?.result ?? []) {
      const symbol = quote.symbol?.toUpperCase();
      if (!symbol) {
        continue;
      }
      const latestPrice = positiveNumber(quote.regularMarketPrice);
      const marketCap = positiveNumber(quote.marketCap);
      const avgVolume = positiveNumber(
        quote.averageDailyVolume3Month ?? quote.averageDailyVolume10Day ?? quote.regularMarketVolume,
      );
      marketData.set(symbol, {
        valid: latestPrice !== undefined || marketCap !== undefined || avgVolume !== undefined,
        latestPrice,
        marketCap,
        avgVolume,
      });
    }
  } catch (error) {
    console.error("Market data lookup failed", error);
  }

  for (const ticker of uniqueTickers) {
    if (!marketData.has(ticker)) {
      marketData.set(ticker, { valid: false });
    }
  }

  return marketData;
}
