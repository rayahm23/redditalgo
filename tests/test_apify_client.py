from scanner.apify_client import _get_run_dataset_id, normalize_apify_item
from scanner.config import ScannerConfig


def test_normalize_apify_item_handles_common_reddit_shapes():
    item = {
        "id": "abc123",
        "subredditName": "r/wallstreetbets",
        "title": "TSLA breakout",
        "body": "I like $nvda too",
        "upVotes": 120,
        "upvoteRatio": 0.91,
        "numComments": 42,
        "createdAt": "2026-05-24T18:00:00Z",
        "url": "/r/wallstreetbets/comments/abc123/tsla_breakout/",
        "comments": [{"body": "AMD is interesting"}, {"text": "YOLO"}],
    }

    post = normalize_apify_item(item, top_comments_limit=3)

    assert post["id"] == "abc123"
    assert post["subreddit"] == "wallstreetbets"
    assert post["title"] == "TSLA breakout"
    assert post["selftext"] == "I like $nvda too"
    assert post["score"] == 120
    assert post["upvote_ratio"] == 0.91
    assert post["num_comments"] == 42
    assert post["permalink"] == "https://reddit.com/r/wallstreetbets/comments/abc123/tsla_breakout/"
    assert post["top_comments"] == ["AMD is interesting", "YOLO"]


def test_default_apify_input_contains_subreddit_hot_and_top_urls():
    config = ScannerConfig(apify_token="token", apify_actor_id="actor")

    run_input = config.get_apify_run_input()
    urls = [entry["url"] for entry in run_input["startUrls"]]

    assert "https://www.reddit.com/r/wallstreetbets/hot/" in urls
    assert "https://www.reddit.com/r/wallstreetbets/top/?t=day" in urls
    assert run_input["maxItems"] == len(config.subreddits) * config.posts_per_listing * 2


def test_normalize_apify_item_leaves_missing_created_utc_as_none():
    item = {
        "id": "abc123",
        "subredditName": "stocks",
        "title": "NVDA setup",
        "body": "Looks strong",
        "createdAt": "not-a-date",
    }

    post = normalize_apify_item(item, top_comments_limit=2)

    assert post["created_utc"] is None


def test_normalize_apify_item_skips_comment_only_shape():
    item = {
        "id": "cmt1",
        "type": "comment",
        "body": "FAQ thread",
        "parentId": "post1",
    }

    post = normalize_apify_item(item, top_comments_limit=2)

    assert post["_comment_only"] is True


def test_apify_input_json_gets_default_max_items():
    config = ScannerConfig(
        apify_token="token",
        apify_actor_id="actor",
        apify_input_json='{"startUrls":[{"url":"https://www.reddit.com/r/stocks/hot/"}]}',
    )

    run_input = config.get_apify_run_input()

    assert run_input["maxItems"] == config.max_apify_items
    assert run_input["maxPosts"] == config.max_apify_items


def test_get_run_dataset_id_supports_dict_and_typed_models():
    class TypedRun:
        default_dataset_id = "typed-dataset-id"

    assert _get_run_dataset_id({"defaultDatasetId": "dict-dataset-id"}) == "dict-dataset-id"
    assert _get_run_dataset_id({"default_dataset_id": "snake-dataset-id"}) == "snake-dataset-id"
    assert _get_run_dataset_id(TypedRun()) == "typed-dataset-id"
