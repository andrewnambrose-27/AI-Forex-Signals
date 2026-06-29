export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Signal = {
  id?: number | null;
  symbol: string;
  timeframe: string;
  direction: string;
  score: number;
  rationale: string;
  risk_flags: string[];
  news_flags: string[];
  created_at?: string | null;
};

export async function scoreSignal(symbol: string, timeframe: string): Promise<Signal> {
  const response = await fetch(`${API_BASE_URL}/api/v1/signals/score`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ symbol, timeframe })
  });

  if (!response.ok) {
    throw new Error("Unable to score signal");
  }

  return response.json();
}
