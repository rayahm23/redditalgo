"""Configuration for the Reddit alpha scanner."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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
}


@dataclass(frozen=True)
class ScannerConfig:
    """Runtime configuration loaded from environment variables."""

    reddit_client_id: str | None
    reddit_client_secret: str | None
    reddit_user_agent: str | None
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
        )

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
