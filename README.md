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
- `data/daily_results.html`
- `data/history/YYYY-MM-DD.json`
- `data/history/YYYY-MM-DD.html`

Each result includes rank, ticker, final score, raw and recency-weighted mention counts, unique posts/users, sentiment, engagement, discussion quality, bullish/bearish attention, market fields, risk flag, risk explanation, score breakdown, summary, top sources, and generation timestamp.

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

## Scoring methodology

The scanner is rule-based and explainable. It is designed to surface better watchlist candidates, not simply the loudest meme tickers.

### Ticker extraction

The scanner supports `$TSLA` cashtags and plain uppercase `TSLA` mentions. It filters common Reddit/trading false positives such as `DD`, `YOLO`, `CEO`, `CFO`, `SEC`, `USA`, `USD`, `AI`, `GDP`, `CPI`, `ETF`, `IPO`, `ATH`, `FOMO`, `IMO`, `LOL`, `OP`, `THE`, `FOR`, `AND`, `ARE`, `YOU`, `NOT`, `PUT`, `CALL`, `ITM`, `OTM`, `ATM`, `RH`, `FED`, `EV`, `EPS`, `PE`, and `IV`. Invalid tickers are removed by yfinance validation before ranking.

### Historical baseline and attention acceleration

Posts are filtered to the last 7 days. Recent posts are weighted more heavily:

- today: `1.00`
- yesterday: `0.85`
- day 2: `0.70`
- day 3: `0.55`
- day 4: `0.40`
- day 5: `0.25`
- day 6: `0.10`

The scanner loads the previous 7 daily history files and calculates:

```text
seven_day_avg_mentions
attention_acceleration = (today_mentions + 3) / (seven_day_avg_mentions + 3)
log_attention_acceleration = log1p(attention_acceleration)
```

`attention_acceleration_score` is log-normalized from 0 to 1, where roughly 4x baseline or higher reaches 1.0.

### Post quality and conviction

Posts are classified with keyword rules as `DD`, `News`, `Earnings`, `Options`, `YOLO`, `Meme`, `Question`, or `Other`. Higher-quality post types receive higher weight:

```text
DD 1.5, News 1.3, Earnings 1.25, Options 1.2, Other 1.0, YOLO 0.8, Meme 0.4, Question 0.3
```

Conviction scoring detects bullish phrases like `buying calls`, `loaded`, `all in`, `adding`, `holding`, `shares`, `leaps`, `squeeze`, `short interest`, `earnings`, `guidance`, `price target`, `PT`, `breakout`, and `unusual volume`, plus bearish phrases like `puts`, `shorting`, `rug pull`, `overvalued`, `dilution`, `bankruptcy`, `selloff`, and `downside`.

Engagement quality favors breadth over raw virality. It uses unique users, comments per post, average upvote ratio, and sustained discussion across multiple posts, with a concentration adjustment so one viral meme post cannot dominate the score by itself.

Discussion quality scores research-oriented language from 0 to 1. Higher-quality terms include `guidance`, `valuation`, `DCF`, `free cash flow`, `FCF`, `margin expansion`, `capex`, `EPS`, `institutional`, and `EBITDA`; lower-quality hype terms include `moon`, `lambo`, `yolo`, `diamond hands`, `ape`, `rocket`, and `trust me bro`. Each result includes `discussion_quality_score`, `high_quality_terms_found`, and `low_quality_terms_found`.

Bullish/bearish attention tracks directional positioning separately from VADER sentiment, including bullish/bearish phrases, puts/calls, accumulation language, and selloff language. Results include `bullish_attention_score`, `bearish_attention_score`, and `net_positioning_score`.

Catalyst detection labels the leading discussion driver when keywords appear for `Earnings`, `AI`, `FDA / biotech`, `Acquisition / M&A`, `Short squeeze`, `Analyst upgrade/downgrade`, `Macro / Fed`, `Options activity`, `Product launch`, and `Legal/regulatory`. Results include `primary_catalyst`, `secondary_catalyst`, and `catalyst_confidence`.

Analyst target scoring uses yfinance `targetMeanPrice`, `targetHighPrice`, `targetLowPrice`, and `recommendationMean` when available. The scanner calculates `analyst_target_upside_pct = (target_mean_price - latest_price) / latest_price` and assigns conservative buckets from major downside through extreme upside; missing target data defaults to a neutral `0.50` score.

### Market confirmation

yfinance is used to add:

- `latest_price`
- `market_cap`
- `avg_volume`
- `one_day_return`
- `five_day_return`
- `relative_volume`
- `above_20_day_high`

`market_confirmation_score` increases with positive 1-day/5-day returns, relative volume above 1.5, and 20-day highs. Low liquidity reduces confirmation.

### Pump/noise risk

`pump_risk_score` is based on hype language, repeated ticker spam, penny-stock/low-volume/small-cap conditions, meme/YOLO-heavy discussion, and cases where sentiment is high but market confirmation is weak.

### Final score

The final score uses this formula and is normalized to 0-100:

```text
final_score =
  0.25 * attention_acceleration_score
+ 0.20 * engagement_quality_score
+ 0.15 * sentiment_score
+ 0.15 * net_conviction_score
+ 0.10 * market_confirmation_score
+ 0.05 * analyst_target_score
+ 0.10 * discussion_quality_score
- pump_risk_penalty
```

Every result includes a `score_breakdown` object explaining these components, including `analyst_target_score`.

## Recommendation types

- `Momentum setup`: stronger score with market confirmation.
- `Possible squeeze`: strong attention acceleration and bullish conviction.
- `Earnings chatter`: discussion dominated by earnings/guidance language.
- `Watchlist`: worth monitoring but not enough confirmation for a stronger label.
- `High-risk pump`: high pump/noise risk.
- `Avoid / too noisy`: low score or weak market confirmation with elevated noise.

Risk flags remain separate from recommendation type:

- `high`: penny stock, low average volume, small market cap, or invalid market data.
- `medium`: valid market data without low-risk liquidity/size signals.
- `low`: larger, liquid tickers with stronger market cap and volume signals.

Each result includes `risk_explanation`, `risk_reasons`, and `risk_thresholds`.

## Backtesting

Run a basic historical forward-return check with:

```bash
python -m scanner.backtest
```

It reads `data/history/*.json`, fetches forward prices with yfinance, and writes `data/backtest_results.json` with next-day, three-day, seven-day, and SPY-relative returns when available. Backtesting is best-effort and does not fail the main scan workflow.

## Limitations

- This is rule-based and heuristic-driven, not predictive ML.
- Reddit posts can be noisy, promotional, sarcastic, or incomplete.
- Apify actor schemas may vary; use `APIFY_INPUT_JSON` if your actor requires custom input.
- yfinance data can be delayed, missing, or rate-limited.
- Backtests are simplistic and do not account for slippage, liquidity, position sizing, or execution.
- No output is financial advice.

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
