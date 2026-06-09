import type { AiStockPicksResponse, AnalysisResponse, ChartResponse, PositionItem, WatchlistItem } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type AnalysisOptions = {
  entryPrice?: number;
  highestPrice?: number;
  atrMultiplier?: number;
};

type AiPicksOptions = {
  universe?: string[];
  limit?: number;
  minScore?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${withCacheBust(path)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function sendJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchAnalysis(symbol: string, options: AnalysisOptions = {}): Promise<AnalysisResponse> {
  const params = new URLSearchParams();
  if (options.entryPrice !== undefined) params.set("entry_price", String(options.entryPrice));
  if (options.highestPrice !== undefined) params.set("highest_price", String(options.highestPrice));
  if (options.atrMultiplier !== undefined) params.set("atr_multiplier", String(options.atrMultiplier));
  const query = params.toString();
  return getJson<AnalysisResponse>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/analysis${query ? `?${query}` : ""}`
  );
}

export async function fetchChart(symbol: string, range = "1y"): Promise<ChartResponse> {
  return getJson<ChartResponse>(`/api/v1/stocks/${encodeURIComponent(symbol)}/chart?range=${range}`);
}

export async function fetchAiPicks(options: AiPicksOptions = {}): Promise<AiStockPicksResponse> {
  const params = new URLSearchParams();
  if (options.universe?.length) params.set("universe", options.universe.join(","));
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.minScore !== undefined) params.set("min_score", String(options.minScore));
  const query = params.toString();
  return getJson<AiStockPicksResponse>(`/api/v1/market/ai-picks${query ? `?${query}` : ""}`);
}

export async function generatePdf(symbol: string): Promise<{ file_path: string }> {
  const response = await fetch(`${API_BASE}/api/v1/reports/${encodeURIComponent(symbol)}/pdf`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`PDF failed: ${response.status}`);
  }
  return response.json() as Promise<{ file_path: string }>;
}

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
  return getJson<WatchlistItem[]>("/api/v1/watchlist");
}

export async function createWatchlistItem(symbol: string): Promise<WatchlistItem> {
  return sendJson<WatchlistItem>("/api/v1/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol })
  });
}

export async function deleteWatchlistItem(id: number): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/api/v1/watchlist/${id}`, {
    method: "DELETE",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<{ status: string }>;
}

export async function fetchPositions(status = "open"): Promise<PositionItem[]> {
  return getJson<PositionItem[]>(`/api/v1/positions?status=${encodeURIComponent(status)}`);
}

export async function savePosition(payload: {
  symbol: string;
  entry_price: number;
  quantity?: number;
  highest_price?: number | null;
}): Promise<PositionItem> {
  return sendJson<PositionItem>("/api/v1/positions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function closePosition(id: number): Promise<PositionItem> {
  const response = await fetch(`${API_BASE}/api/v1/positions/${id}`, {
    method: "DELETE",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<PositionItem>;
}

function withCacheBust(path: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}_=${Date.now()}`;
}
