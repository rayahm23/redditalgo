# reddit-alpha-scanner

Devvit-first MVP for a Reddit stock sentiment watchlist. The app runs inside Reddit, scans public investing subreddits on a schedule, ranks stock tickers by Reddit attention/sentiment, validates symbols with Yahoo Finance quote data, stores the latest result in Devvit Redis, and displays the watchlist in a custom Reddit post.

This is a research/watchlist tool only. It does not auto-trade, post comments, vote, message users, train AI models, or identify Reddit users.

## What it scans

Daily scheduled scans and moderator-triggered scans read hot and top daily posts from:

- `wallstreetbets`
- `stocks`
- `investing`
- `pennystocks`
- `options`
- `shortsqueeze`

For each post the server collects title, body, score, comment count, created time, permalink, and a few top comments.

## How ranking works

The scanner extracts `$TSLA` style and plain uppercase `TSLA` style tickers, filters common false positives, scores VADER sentiment across title/body/comments, validates market data, and ranks up to 15 tickers using:

- mention count
- unique posts
- total upvotes
- average sentiment
- comment volume
- market validity
- risk penalty

Risk flags:

- `high`: penny stock, low average volume, small market cap, or invalid market data
- `medium`: valid market data without low-risk size/liquidity signals
- `low`: larger, liquid tickers with stronger market cap and volume signals

## Devvit setup

Prerequisites:

- Node.js 22.2+
- Reddit developer account connected to Devvit
- A small subreddit you moderate for playtesting

Install dependencies:

```bash
npm install
```

Login to Devvit:

```bash
npx devvit login
```

If you have not created a Devvit app yet, go to:

```text
https://developers.reddit.com/new
```

This repo uses the Devvit app name `alpha-scanner` in `devvit.json`.

## Run locally / playtest

Build and test locally:

```bash
npm run build
npm test
```

Start a Devvit playtest. You can set your own test subreddit with `DEVVIT_SUBREDDIT`:

```bash
DEVVIT_SUBREDDIT=your_test_subreddit npm run dev
```

In the test subreddit, use the subreddit moderator menu items:

1. **Create Reddit Alpha Scanner post**
2. **Run Reddit Alpha scan now**

The custom post displays the latest Redis-stored scan result. The scheduled task runs daily at `15 12 * * *`, around 8:15 AM New York time during daylight saving time.

## Deploy/review

Upload a private test version:

```bash
npm run upload
```

Submit for Reddit review when ready:

```bash
npm run publish
```

## Notes and limitations

- Devvit uses Reddit-native API access, so this version does not use PRAW or Reddit client secrets.
- Market validation uses the Yahoo Finance quote endpoint through Devvit server-side HTTP permissions.
- Redis is installation-scoped, so each subreddit installation has its own latest scan result.
- The scan is intentionally capped per run to stay within Devvit serverless request limits.

## Disclaimer

Not financial advice. This app is for research and watchlist generation only. Always do your own research and consider consulting a licensed financial professional.
