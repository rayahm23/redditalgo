"""Configuration for the Reddit alpha scanner."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


SUBREDDITS = (
    "wallstreetbets",
    "stocks",
    "investing",
    "pennystocks",
    "options",
    "shortsqueeze",
)

EXCLUDED_TICKERS = {
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
    "PUT",
    "CALL",
    "ITM",
    "OTM",
    "ATM",
    "RH",
    "FED",
    "EV",
    "EPS",
    "PE",
    "IV",
}


@dataclass(frozen=True)
class ScannerConfig:
    """Runtime configuration loaded from environment variables."""

    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None
    reddit_backend: str = "apify"
    apify_token: str | None = None
    apify_actor_id: str | None = None
    apify_input_json: str | None = None
    subreddits: tuple[str, ...] = SUBREDDITS
    posts_per_listing: int = 35
    top_comments_per_post: int = 8
    output_path: Path = Path("data/daily_results.json")
    history_dir: Path = Path("data/history")
    excluded_tickers: set[str] = field(default_factory=lambda: set(EXCLUDED_TICKERS))

    @classmethod
    def from_env(cls) -> "ScannerConfig":
        """Load .env values for local runs and return a config object."""

        load_dotenv()
        return cls(
            reddit_client_id=os.getenv("REDDIT_CLIENT_ID"),
            reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            reddit_user_agent=os.getenv("REDDIT_USER_AGENT"),
            reddit_backend=os.getenv("REDDIT_BACKEND", "apify").lower(),
            apify_token=os.getenv("APIFY_TOKEN"),
            apify_actor_id=os.getenv("APIFY_ACTOR_ID"),
            apify_input_json=os.getenv("APIFY_INPUT_JSON"),
        )

    @property
    def max_apify_items(self) -> int:
        """Return a conservative max item count for Apify actor runs."""

        return len(self.subreddits) * self.posts_per_listing * 2

    def get_apify_run_input(self) -> dict[str, Any]:
        """Return actor input from APIFY_INPUT_JSON or a generic Reddit scraper shape."""

        if self.apify_input_json:
            parsed = json.loads(self.apify_input_json)
            if not isinstance(parsed, dict):
                raise ValueError("APIFY_INPUT_JSON must decode to a JSON object")
            return parsed

        start_urls = []
        for subreddit in self.subreddits:
            start_urls.extend(
                [
                    {"url": f"https://www.reddit.com/r/{subreddit}/hot/"},
                    {"url": f"https://www.reddit.com/r/{subreddit}/top/?t=day"},
                ]
            )

        # Reddit scraper actors have different input schemas. This generic shape
        # works for many actors and can be overridden entirely with APIFY_INPUT_JSON.
        return {
            "startUrls": start_urls,
            "maxItems": self.max_apify_items,
            "maxPosts": self.max_apify_items,
            "maxComments": self.top_comments_per_post,
            "proxyConfiguration": {"useApifyProxy": True},
        }

    def validate_reddit_credentials(self) -> None:
        """Raise a helpful error when Reddit credentials are missing."""

        missing = [
            name
            for name, value in {
                "REDDIT_CLIENT_ID": self.reddit_client_id,
                "REDDIT_CLIENT_SECRET": self.reddit_client_secret,
                "REDDIT_USER_AGENT": self.reddit_user_agent,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing Reddit API environment variables: " + ", ".join(missing)
            )

    def validate_apify_credentials(self) -> None:
        """Raise a helpful error when Apify configuration is missing."""

        missing = [
            name
            for name, value in {
                "APIFY_TOKEN": self.apify_token,
                "APIFY_ACTOR_ID": self.apify_actor_id,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError("Missing Apify environment variables: " + ", ".join(missing))
