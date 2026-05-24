# reddit-alpha-scanner

A functional MVP for a daily Reddit stock sentiment scanner. It runs as a Python 3.11 data pipeline, pulls Reddit post data through an Apify Reddit scraper actor by default, extracts stock tickers, scores attention and sentiment, validates symbols with market data, ranks the top tickers, and writes JSON watchlist results.

This is a research/watchlist tool only. It does not trade, place orders, post to Reddit, vote, message users, or provide financial advice.

## What it scans

The scanner is configured for:

- `wallstreetbets`
- `stocks`
- `investing`
- `pennystocks`
- `options`
- `shortsqueeze`

For each normalized post it uses subreddit, title, body/selftext, score, upvote ratio, comment count, creation time, permalink, and top comments when the Apify actor provides them.

## Backend options

### Default: Apify

Set:

```bash
REDDIT_BACKEND=apify
APIFY_TOKEN=...
APIFY_ACTOR_ID=...
```

`APIFY_ACTOR_ID` should be the actor ID for the Reddit scraper you want to run, such as `username/actor-name` or an actor ID copied from Apify.

Different Apify Reddit scraper actors use different input schemas. The scanner sends a generic input with `startUrls`, `maxItems`, `maxPosts`, `maxComments`, and Apify proxy enabled. If your chosen actor needs a specific schema, set `APIFY_INPUT_JSON` to override the input completely:

```bash
APIFY_INPUT_JSON={"startUrls":[{"url":"https://www.reddit.com/r/wallstreetbets/hot/"}],"maxItems":100}
```

### Optional fallback: PRAW

If you receive Reddit API approval, you can still use the original PRAW backend:

```bash
REDDIT_BACKEND=praw
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=reddit-alpha-scanner/0.1 by your_reddit_username
```

## Output

The top 15 ranked tickers are written to:

- `data/daily_results.json`
- `data/history/YYYY-MM-DD.json`

Each result includes rank, ticker, final score, mention counts, unique posts, sentiment, engagement, market fields, risk flag, summary, top sources, and generation timestamp.

## Local setup

Python 3.11 is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your Apify values:

```bash
REDDIT_BACKEND=apify
APIFY_TOKEN=your_apify_api_token
APIFY_ACTOR_ID=your_apify_reddit_scraper_actor_id
```

Run the scan:

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

### Add GitHub Secrets for Apify

In your GitHub repository:

1. Go to **Settings** -> **Secrets and variables** -> **Actions**.
2. Add these repository secrets:
   - `APIFY_TOKEN`
   - `APIFY_ACTOR_ID`
   - Optional: `APIFY_INPUT_JSON` if your actor needs custom input.
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

## Compliance note

Apify actor usage depends on the actor and the data source terms that apply to it. Use a compliant actor, respect Reddit and Apify policies, avoid excessive collection, and keep this project read-only and personal/non-commercial unless you have the required approvals.

## Disclaimer

This project is for research and watchlist generation only. It is not financial advice, investment advice, or a recommendation to buy or sell securities. Always do your own research and consider consulting a licensed financial professional.
