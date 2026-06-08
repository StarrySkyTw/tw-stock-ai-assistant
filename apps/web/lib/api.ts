import type { AnalysisResponse, ChartResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type AnalysisOptions = {
  entryPrice?: number;
  highestPrice?: number;
  atrMultiplier?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
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

export async function generatePdf(symbol: string): Promise<{ file_path: string }> {
  const response = await fetch(`${API_BASE}/api/v1/reports/${encodeURIComponent(symbol)}/pdf`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`PDF failed: ${response.status}`);
  }
  return response.json() as Promise<{ file_path: string }>;
}
