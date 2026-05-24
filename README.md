# reddit-alpha-scanner

A functional MVP for a daily Reddit stock sentiment scanner. It runs as a Python 3.11 data pipeline, pulls Reddit post data through an Apify Reddit scraper actor by default, extracts stock tickers, scores attention and sentiment, validates symbols with market data, ranks the top tickers, and writes JSON watchlist results.

This is a research/watchlist tool only. It does not trade, place orders, post to Reddit, vote, message users, or provide financial advice.

## What it scans

The scanner monitors weighted subreddit groups:

- **High-quality discussion:** `SecurityAnalysis`, `ValueInvesting`, `stocks`, `investing`, `StockMarket`, `options`, `thetagang`, `wallstreetbetsOGs`
- **High-momentum retail:** `wallstreetbets`, `Daytrading`, `SwingTrading`, `Trading`, `smallstreetbets`, `Shortsqueeze`, `squeezeplays`, `WallstreetbetsELITE`
- **Growth / speculative but investable:** `GrowthStocks`, `FutureInvesting`, `hypergrowthstocks`, `SPACs`, `biotech_stocks`, `stocksandtrading`

Lower-quality momentum subs (for example `Shortsqueeze`, `WallstreetbetsELITE`) are **not ignored**, but they carry lower weights and need corroboration from higher-quality subs to rank near the top.

For each normalized post it uses subreddit, title, body/selftext, score, comment volume, creation time, permalink, top comments, and author when available.

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

Each result includes rank, ticker, final score, signal confidence, recommendation type, historical 7-day trends, sparkline-ready series, raw and recency-weighted mention counts, unique posts, sentiment, engagement, market fields, risk flag, risk explanation, score breakdown, summary, top sources, and generation timestamp.

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
attention_acceleration = today_mentions / max(seven_day_avg_mentions, 1)
```

`attention_acceleration_score` is normalized from 0 to 1, where roughly 4x baseline or higher reaches 1.0.

When prior daily history exists, mention acceleration uses an exponentially smoothed 7-day mention series (`smooth_series`) so single-day spikes do not dominate the score. The smoothed recent level is compared against the trailing baseline from the same series.

### Historical trends and sparklines

Each ranked ticker stores trailing 7-day arrays under `historical_trends`:

```json
{
  "mentions_7d": [],
  "sentiment_7d": [],
  "score_7d": [],
  "analyst_target_upside_7d": []
}
```

Arrays are oldest-to-newest and include the current scan as the final point. The companion `sparklines` object mirrors these arrays for chart widgets (`mentions`, `sentiment`, `score`, `analyst_target_upside`, `length`). `trend_dates` provides the ISO dates aligned to each index.

The HTML report renders compact inline sparklines plus chips for analyst upside, confidence level, and catalyst type.

### Post quality and conviction

Posts are classified with keyword rules as `DD`, `News`, `Earnings`, `Options`, `YOLO`, `Meme`, `Question`, or `Other`. Higher-quality post types receive higher weight:

```text
DD 1.5, News 1.3, Earnings 1.25, Options 1.2, Other 1.0, YOLO 0.8, Meme 0.4, Question 0.3
```

Conviction scoring detects bullish phrases like `buying calls`, `loaded`, `all in`, `adding`, `holding`, `shares`, `leaps`, `squeeze`, `short interest`, `earnings`, `guidance`, `price target`, `PT`, `breakout`, and `unusual volume`, plus bearish phrases like `puts`, `shorting`, `rug pull`, `overvalued`, `dilution`, `bankruptcy`, `selloff`, and `downside`.

### Analyst target logic

`analyst_target_score` (also tracked in `analyst_target_upside_7d`) measures upside-oriented sell-side language in post titles, bodies, and comments. Keyword hits include `price target`, `analyst`, `upgrade`, `downgrade`, `outperform`, `overweight`, `consensus`, and similar phrases. The per-post score caps at 1.0 after three hits; the ticker-level score uses the maximum post-level score in the window.

Strong analyst language plus high `discussion_quality_score` routes to the `Analyst upside watch` recommendation bucket.

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

### Speculative activity vs volatility

`pump_risk_score` measures **low-quality speculation** (spam hype, meme-only threads, sub-$2 penny profiles, extreme illiquidity, microcap + weak discussion). It does **not** penalize volatility, momentum, or smaller high-growth names by themselves.

`market_confirmation_score` rewards strong 5-day performance, elevated relative volume, breakouts above the 20-day high, and sustained participation. Pullbacks are lightly penalized, not treated like pump risk.

### Final score

The final score uses this formula and is normalized to 0-100:

```text
final_score =
  0.25 * attention_acceleration_score
+ 0.20 * engagement_quality_score
+ 0.15 * sentiment_score
+ 0.15 * net_conviction_score
+ 0.15 * market_confirmation_score
+ 0.10 * subreddit_spread_score
- pump_risk_penalty
```

Every result includes a `score_breakdown` object explaining these components.

## Subreddit weighting

Each post inherits a subreddit weight (for example `SecurityAnalysis` = 1.4, `wallstreetbets` = 1.0, `Shortsqueeze` = 0.7). Weights influence:

- `engagement_quality_score`
- `discussion_quality_score`
- `signal_confidence_score`

Exported fields include `subreddit_groups_detected`, `top_signal_subreddits`, `noisy_subreddit_exposure`, and `subreddit_weighted_score`.

If a subreddit is private, banned, or unavailable, the fetch step skips it and continues.

## Narrative extraction

`scanner/narrative_extraction.py` summarizes **what users are discussing**, not just that mentions rose.

Each ticker exports:

- `primary_narrative`
- `bullish_themes`, `bearish_themes`, `neutral_themes`
- `narrative_confidence` / `narrative_confidence_score`
- `narrative_keywords`

Summaries in JSON/HTML use these themes when confidence is sufficient. Rule-based theme matching has limitations: sarcasm, typos, and sparse samples can produce `LOW` confidence or the fallback message:

`Discussion was too limited or scattered to identify a clear narrative.`

## Signal confidence

Each ranked ticker includes:

- `signal_confidence_score`: 0-1 composite from subreddit spread, discussion quality, analyst target language, market confirmation, low pump risk, unique users, and catalyst confidence.
- `signal_confidence_label`: `LOW`, `MEDIUM`, or `HIGH`.

Supporting component fields are also exported (`discussion_quality_score`, `analyst_target_score`, `catalyst_confidence_score`, `unique_users_score`, `unique_users`).

## Recommendation types

- `Analyst upside watch`: strong analyst/upside language with high discussion quality.
- `Volatile momentum setup`: strong score with market confirmation and rising attention.
- `Strong retail acceleration`: sharp mention acceleration with acceptable discussion quality.
- `High-upside catalyst trade`: earnings or AI-led catalyst with market support.
- `Aggressive growth watch`: momentum-driven growth name worth tracking.
- `Panic selloff`: elevated bearish attention and negative sentiment.
- `Institutional-style accumulation`: strong discussion quality with limited low-quality hype.
- `Contrarian watchlist`: negative sentiment with moderate quality and manageable noise.
- `Watchlist`: worth monitoring but not enough confirmation for a stronger label.
- `Low-quality pump`: illiquid penny-style pump or meme-only spam profile.
- `Avoid / too noisy`: low score or very weak discussion quality with elevated noise.

Investability flags (`risk_flag`) are separate from recommendation type:

- `high`: sub-$2 price or extremely low liquidity (<150k average volume), or invalid market data.
- `medium`: investable profile, including volatile momentum names.
- `low`: large, liquid large-cap profile.

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
- Historical trends require prior `data/history/YYYY-MM-DD.json` snapshots; early runs pad missing days with zeros.
- Mention acceleration smoothing depends on consistent daily scans; skipped days reduce trend fidelity.
- Author-based unique-user scoring is only available when the Reddit/Apify payload includes author fields.
- Apify actor schemas may vary; use `APIFY_INPUT_JSON` if your actor requires custom input.
- yfinance data can be delayed, missing, or rate-limited.
- Backtests are simplistic and do not account for slippage, liquidity, position sizing, or execution.
- Catalyst and recommendation labels are heuristic tags, not verified event classifications.
- No output is financial advice.

## Dashboard / GitHub Pages

The static HTML report at `data/daily_results.html` (also deployed via GitHub Pages) includes:

- ranked cards with score, recommendation, and risk
- chips for analyst upside, confidence level (`LOW` / `MEDIUM` / `HIGH`), and catalyst type
- inline 7-day sparklines for mentions, sentiment, score, and analyst upside
- expandable score breakdown, risk notes, and Reddit source links

A separate Vercel dashboard can still read `data/daily_results.json` directly and bind the `sparklines` arrays to chart components.

## Compliance note

Apify actor usage depends on the actor and the data source terms that apply to it. Use a compliant actor, respect Reddit and Apify policies, avoid excessive collection, and keep this project read-only and personal/non-commercial unless you have the required approvals.

## Disclaimer

This project is for research and watchlist generation only. It is not financial advice, investment advice, or a recommendation to buy or sell securities. Always do your own research and consider consulting a licensed financial professional.
