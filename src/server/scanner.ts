import type { RedditClient } from "@devvit/web/server";
import { redis } from "@devvit/web/server";
import {
  MAX_MARKET_LOOKUPS,
  POSTS_PER_LISTING,
  SCAN_RESULT_KEY,
  SUBREDDITS,
  TOP_COMMENTS_PER_POST,
  TOP_RESULT_LIMIT,
} from "../shared/config.js";
import { getMarketDataForTickers } from "../shared/marketData.js";
import { aggregatePosts, rankTickers } from "../shared/scoring.js";
import type { ScanPayload, SourcePost } from "../shared/types.js";

async function collectComments(redditClient: RedditClient, postId: string): Promise<string[]> {
  try {
    const comments = await redditClient
      .getComments({ postId, limit: TOP_COMMENTS_PER_POST, pageSize: TOP_COMMENTS_PER_POST, sort: "top" })
      .all();
    return comments.map((comment) => comment.body).filter(Boolean);
  } catch (error) {
    console.error(`Failed to collect comments for ${postId}`, error);
    return [];
  }
}

async function postToSourcePost(redditClient: RedditClient, post: Awaited<ReturnType<RedditClient["getPostById"]>>): Promise<SourcePost> {
  return {
    id: post.id,
    subreddit: post.subredditName,
    title: post.title,
    selftext: post.body ?? "",
    score: post.score,
    numComments: post.numberOfComments,
    createdUtc: Math.floor(post.createdAt.getTime() / 1000),
    permalink: post.permalink.startsWith("http") ? post.permalink : `https://reddit.com${post.permalink}`,
    topComments: await collectComments(redditClient, post.id),
  };
}

export async function fetchRedditPosts(redditClient: RedditClient): Promise<SourcePost[]> {
  const posts: SourcePost[] = [];
  const seenIds = new Set<string>();

  for (const subredditName of SUBREDDITS) {
    const listings = [
      redditClient.getHotPosts({ subredditName, limit: POSTS_PER_LISTING, pageSize: POSTS_PER_LISTING }),
      redditClient.getTopPosts({ subredditName, timeframe: "day", limit: POSTS_PER_LISTING, pageSize: POSTS_PER_LISTING }),
    ];

    for (const listing of listings) {
      try {
        const listingPosts = await listing.all();
        for (const post of listingPosts) {
          if (seenIds.has(post.id)) {
            continue;
          }
          seenIds.add(post.id);
          posts.push(await postToSourcePost(redditClient, post));
        }
      } catch (error) {
        console.error(`Failed to scan r/${subredditName}`, error);
      }
    }
  }

  return posts;
}

export async function runScan(redditClient: RedditClient): Promise<ScanPayload> {
  const generatedAt = new Date().toISOString();
  const posts = await fetchRedditPosts(redditClient);
  const aggregates = aggregatePosts(posts);
  const candidateTickers = [...aggregates.keys()].slice(0, MAX_MARKET_LOOKUPS);
  const marketData = await getMarketDataForTickers(candidateTickers);
  const results = rankTickers(aggregates, marketData, generatedAt, TOP_RESULT_LIMIT);

  return {
    generated_at: generatedAt,
    subreddits: [...SUBREDDITS],
    results,
  };
}

export async function saveScan(payload: ScanPayload): Promise<void> {
  await redis.set(SCAN_RESULT_KEY, JSON.stringify(payload));
}

export async function loadLatestScan(): Promise<ScanPayload | undefined> {
  const value = await redis.get(SCAN_RESULT_KEY);
  return value ? (JSON.parse(value) as ScanPayload) : undefined;
}
