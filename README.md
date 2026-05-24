# reddit-alpha-scanner

A functional MVP for a daily Reddit stock sentiment scanner. It pulls Reddit posts from investing-focused subreddits, extracts stock tickers, scores attention and sentiment, validates symbols with market data, ranks the top tickers, and writes JSON watchlist results.

This is a research/watchlist tool only. It does not trade, place orders, or provide financial advice.

## What it scans

The scanner pulls hot and daily top posts from:

- `wallstreetbets`
- `stocks`
- `investing`
- `pennystocks`
- `options`
- `shortsqueeze`

For each post it collects subreddit, title, body, score, upvote ratio, comment count, creation time, permalink, and top comments.

## Output

The top 15 ranked tickers are written to:

- `data/daily_results.json`
- `data/history/YYYY-MM-DD.json`

Each result includes rank, ticker, final score, mention counts, unique posts, sentiment, engagement, market fields, risk flag, summary, top sources, and generation timestamp.

## Setup

### 1. Create Reddit API credentials

1. Sign in to Reddit.
2. Visit <https://www.reddit.com/prefs/apps>.
3. Select **create another app**.
4. Choose **script** as the app type.
5. Set a name such as `reddit-alpha-scanner`.
6. Set redirect URI to `http://localhost:8080`.
7. Save the app.
8. Copy the client ID shown under the app name and the client secret.

### 2. Configure local environment

```bash
cp .env.example .env
```

Fill in:

```bash
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=reddit-alpha-scanner/0.1 by your_reddit_username
```

### 3. Install dependencies

Python 3.11 is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run locally

```bash
python -m scanner.pipeline
```

Run tests:

```bash
pytest
```

## GitHub Actions

The workflow at `.github/workflows/daily_scan.yml` can be run manually with `workflow_dispatch` and runs daily by cron.

The cron is set to `15 12 * * *`, which corresponds to about 8:15 AM New York time during daylight saving time. GitHub cron uses UTC; adjust the cron seasonally if you require exact New York local time year-round.

### Add GitHub Secrets

In your GitHub repository:

1. Go to **Settings** -> **Secrets and variables** -> **Actions**.
2. Add these repository secrets:
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`
   - `REDDIT_USER_AGENT`
3. Go to **Actions** -> **Daily Reddit Alpha Scan** -> **Run workflow** to trigger a manual scan.

The workflow installs dependencies, runs `python -m scanner.pipeline`, and commits updated JSON files back to the repository.

## Scoring model

The final score is an explainable 0-100 value based on:

- mention count
- number of unique Reddit posts
- total upvotes
- average sentiment
- comment volume
- market data validity
- risk penalty

Risk is flagged as:

- `high`: penny stock, low average volume, small market cap, or invalid market data
- `medium`: valid market data without low-risk liquidity/size signals
- `low`: larger, liquid tickers with stronger market cap and volume signals

## Future Vercel dashboard

A Vercel dashboard can read `data/daily_results.json` directly from the repository or from a lightweight API route that fetches the raw GitHub file. Suggested first dashboard views:

- ranked ticker table
- risk flag filters
- sentiment and attention columns
- links to top Reddit sources
- history chart sourced from `data/history/*.json`

## Disclaimer

This project is for research and watchlist generation only. It is not financial advice, investment advice, or a recommendation to buy or sell securities. Always do your own research and consider consulting a licensed financial professional.
