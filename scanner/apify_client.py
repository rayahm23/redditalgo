"""Apify Reddit scraper integration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from apify_client import ApifyClient

from scanner.config import ScannerConfig


TEXT_COMMENT_KEYS = ("body", "text", "comment", "content")
COMMENT_LIST_KEYS = (
    "top_comments",
    "topComments",
    "comments",
    "commentList",
    "latestComments",
)


def _first_value(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_created_utc(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        # Some actors return milliseconds, Reddit/PRAW returns seconds.
        return float(value / 1000 if value > 10_000_000_000 else value)
    if isinstance(value, str):
        try:
            return _parse_created_utc(float(value))
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0
    return 0.0


def _normalize_subreddit(value: Any, permalink: str = "") -> str:
    if isinstance(value, dict):
        value = _first_value(value, "name", "displayName", "display_name", default="")
    subreddit = str(value or "").strip()
    if subreddit.startswith("r/"):
        subreddit = subreddit[2:]
    if subreddit:
        return subreddit

    parsed = urlparse(permalink)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "r":
        return parts[1]
    return ""


def _normalize_permalink(value: Any) -> str:
    permalink = str(value or "").strip()
    if not permalink:
        return ""
    if permalink.startswith("/"):
        return f"https://reddit.com{permalink}"
    return permalink


def _extract_comments(item: dict[str, Any], limit: int) -> list[str]:
    for key in COMMENT_LIST_KEYS:
        raw_comments = item.get(key)
        if not raw_comments:
            continue
        if isinstance(raw_comments, str):
            return [raw_comments][:limit]
        if not isinstance(raw_comments, list):
            continue

        comments: list[str] = []
        for raw_comment in raw_comments:
            if isinstance(raw_comment, str):
                body = raw_comment
            elif isinstance(raw_comment, dict):
                body = str(_first_value(raw_comment, *TEXT_COMMENT_KEYS, default=""))
            else:
                body = ""
            if body:
                comments.append(body)
            if len(comments) >= limit:
                break
        return comments
    return []


def normalize_apify_item(item: dict[str, Any], top_comments_limit: int) -> dict[str, Any]:
    """Normalize a Reddit-shaped Apify dataset item to the scanner post schema."""

    permalink = _normalize_permalink(_first_value(item, "permalink", "url", "link", default=""))
    subreddit = _normalize_subreddit(
        _first_value(item, "subreddit", "subredditName", "communityName", "community", default=""),
        permalink,
    )
    post_id = str(_first_value(item, "id", "postId", "redditId", "fullName", default=permalink))

    return {
        "id": post_id,
        "subreddit": subreddit,
        "title": str(_first_value(item, "title", "heading", default="") or ""),
        "selftext": str(_first_value(item, "selftext", "body", "text", "description", default="") or ""),
        "score": _to_int(_first_value(item, "score", "upvotes", "upVotes", "ups", default=0)),
        "upvote_ratio": _to_float(_first_value(item, "upvote_ratio", "upvoteRatio", default=0.0)),
        "num_comments": _to_int(
            _first_value(item, "num_comments", "numComments", "commentCount", "commentsCount", default=0)
        ),
        "created_utc": _parse_created_utc(
            _first_value(item, "created_utc", "createdUtc", "createdAt", "date", "timestamp", default=0)
        ),
        "permalink": permalink,
        "top_comments": _extract_comments(item, top_comments_limit),
    }


def fetch_apify_posts(config: ScannerConfig) -> list[dict[str, Any]]:
    """Run an Apify Reddit scraper actor and return normalized Reddit posts."""

    config.validate_apify_credentials()
    client = ApifyClient(config.apify_token)
    run = client.actor(config.apify_actor_id).call(run_input=config.get_apify_run_input())
    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("Apify actor run did not return a default dataset")

    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in client.dataset(dataset_id).iterate_items():
        if not isinstance(item, dict):
            continue
        post = normalize_apify_item(item, config.top_comments_per_post)
        post_id = str(post.get("id") or post.get("permalink"))
        if post_id and post_id in seen_ids:
            continue
        if post_id:
            seen_ids.add(post_id)
        if post.get("title") or post.get("selftext"):
            posts.append(post)

    return posts
