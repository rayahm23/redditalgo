"""PRAW client and Reddit post collection."""

from __future__ import annotations

from typing import Any

import praw
from praw.models import MoreComments

from scanner.config import ScannerConfig


def create_reddit_client(config: ScannerConfig) -> praw.Reddit:
    """Create a read-only Reddit client from scanner config."""

    config.validate_reddit_credentials()
    return praw.Reddit(
        client_id=config.reddit_client_id,
        client_secret=config.reddit_client_secret,
        user_agent=config.reddit_user_agent,
        check_for_async=False,
    )


def _collect_top_comments(submission: Any, limit: int) -> list[str]:
    """Collect top-level comments after replacing MoreComments placeholders."""

    comments: list[str] = []
    try:
        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
    except Exception:
        return comments

    for comment in submission.comments[:limit]:
        if isinstance(comment, MoreComments):
            continue
        body = getattr(comment, "body", "")
        if body:
            comments.append(body)
    return comments


def _submission_to_dict(submission: Any, top_comments_limit: int) -> dict[str, Any]:
    permalink = getattr(submission, "permalink", "")
    if permalink and permalink.startswith("/"):
        permalink = f"https://reddit.com{permalink}"

    return {
        "id": getattr(submission, "id", None),
        "subreddit": str(getattr(submission, "subreddit", "")),
        "title": getattr(submission, "title", "") or "",
        "selftext": getattr(submission, "selftext", "") or "",
        "author": str(getattr(submission, "author", "") or ""),
        "score": int(getattr(submission, "score", 0) or 0),
        "upvote_ratio": float(getattr(submission, "upvote_ratio", 0) or 0),
        "num_comments": int(getattr(submission, "num_comments", 0) or 0),
        "created_utc": float(getattr(submission, "created_utc", 0) or 0),
        "permalink": permalink,
        "top_comments": _collect_top_comments(submission, top_comments_limit),
    }


def fetch_reddit_posts(config: ScannerConfig) -> list[dict[str, Any]]:
    """Pull hot and daily top submissions from configured subreddits."""

    reddit = create_reddit_client(config)
    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for subreddit_name in config.subreddits:
        subreddit = reddit.subreddit(subreddit_name)
        listings = (
            subreddit.hot(limit=config.posts_per_listing),
            subreddit.top(time_filter="day", limit=config.posts_per_listing),
        )
        for listing in listings:
            for submission in listing:
                post_id = str(getattr(submission, "id", ""))
                if post_id and post_id in seen_ids:
                    continue
                if post_id:
                    seen_ids.add(post_id)
                posts.append(_submission_to_dict(submission, config.top_comments_per_post))

    return posts
