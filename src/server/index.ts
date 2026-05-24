import { once } from "node:events";
import type { IncomingMessage, ServerResponse } from "node:http";
import { createServer, getServerPort, reddit } from "@devvit/web/server";
import type { ScanPayload } from "../shared/types.js";
import { loadLatestScan, runScan, saveScan } from "./scanner.js";

type JsonValue = Record<string, unknown> | unknown[] | string | number | boolean | null;

type UiResponse = {
  showToast?: {
    text: string;
    appearance?: "success" | "neutral" | "warning" | "error";
  };
  navigateTo?: string;
};

async function readJson<T>(req: IncomingMessage): Promise<T | undefined> {
  const chunks: Uint8Array[] = [];
  req.on("data", (chunk: Uint8Array) => chunks.push(chunk));
  await once(req, "end");
  if (chunks.length === 0) {
    return undefined;
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as T;
}

function writeJson(status: number, body: JsonValue, res: ServerResponse): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-length": Buffer.byteLength(payload),
    "content-type": "application/json; charset=utf-8",
  });
  res.end(payload);
}

async function handleRunScan(): Promise<ScanPayload> {
  const payload = await runScan(reddit);
  await saveScan(payload);
  return payload;
}

async function handleCreatePost(): Promise<UiResponse> {
  const post = await reddit.submitCustomPost({ title: "Reddit Alpha Scanner" });
  return {
    showToast: { text: "Created Reddit Alpha Scanner post.", appearance: "success" },
    navigateTo: post.url,
  };
}

async function route(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const method = req.method ?? "GET";
  const url = new URL(req.url ?? "/", "http://localhost");

  if (method === "GET" && url.pathname === "/api/results") {
    writeJson(200, (await loadLatestScan()) ?? { generated_at: null, subreddits: [], results: [] }, res);
    return;
  }

  if (method === "POST" && url.pathname === "/internal/menu/create-post") {
    await readJson(req).catch(() => undefined);
    writeJson(200, await handleCreatePost(), res);
    return;
  }

  if (method === "POST" && url.pathname === "/internal/menu/run-scan") {
    await readJson(req).catch(() => undefined);
    const payload = await handleRunScan();
    writeJson(200, {
      showToast: { text: `Scan complete: ${payload.results.length} tickers ranked.`, appearance: "success" },
    }, res);
    return;
  }

  if (method === "POST" && url.pathname === "/internal/scheduler/daily-scan") {
    await readJson(req).catch(() => undefined);
    await handleRunScan();
    writeJson(200, {}, res);
    return;
  }

  writeJson(404, { error: "not found", status: 404 }, res);
}

async function onRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  try {
    await route(req, res);
  } catch (error) {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    console.error(message);
    writeJson(500, { error: message, status: 500 }, res);
  }
}

const server = createServer(onRequest);
const port = getServerPort();
server.on("error", (error) => console.error(`server error: ${error.stack}`));
server.listen(port);
