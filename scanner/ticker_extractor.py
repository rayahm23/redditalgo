"""Stock ticker extraction utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scanner.config import EXCLUDED_TICKERS

# Cashtags can include one-letter tickers such as $F. Plain words are limited to
# 2-5 characters to reduce noise from ordinary single-letter initials.
CASHTAG_PATTERN = re.compile(r"(?<![A-Za-z0-9_])\$([A-Za-z]{1,5})(?![A-Za-z])")
PLAIN_TICKER_PATTERN = re.compile(r"(?<!\$)\b[A-Z]{2,5}\b")


def normalize_ticker(candidate: str) -> str:
    """Normalize a possible ticker symbol to uppercase letters only."""

    return candidate.strip().lstrip("$").upper()


def is_probable_ticker(candidate: str, excluded: set[str] | None = None) -> bool:
    """Return True when a candidate passes MVP ticker heuristics."""

    excluded_symbols = excluded if excluded is not None else EXCLUDED_TICKERS
    ticker = normalize_ticker(candidate)
    return bool(
        1 <= len(ticker) <= 5
        and ticker.isalpha()
        and ticker not in excluded_symbols
    )


def extract_tickers_from_text(
    text: str | None, excluded: set[str] | None = None
) -> list[str]:
    """Extract normalized ticker mentions from text, preserving duplicates."""

    if not text:
        return []

    tickers: list[str] = []
    for match in CASHTAG_PATTERN.findall(text):
        ticker = normalize_ticker(match)
        if is_probable_ticker(ticker, excluded):
            tickers.append(ticker)

    for match in PLAIN_TICKER_PATTERN.findall(text):
        ticker = normalize_ticker(match)
        if is_probable_ticker(ticker, excluded):
            tickers.append(ticker)

    return tickers


def extract_tickers_from_post(
    title: str | None,
    selftext: str | None,
    comments: Iterable[str] | None = None,
    excluded: set[str] | None = None,
) -> list[str]:
    """Extract ticker mentions from a Reddit post and its top comments."""

    mentions: list[str] = []
    mentions.extend(extract_tickers_from_text(title, excluded))
    mentions.extend(extract_tickers_from_text(selftext, excluded))
    for comment in comments or []:
        mentions.extend(extract_tickers_from_text(comment, excluded))
    return mentions
