import type { CandlestickData, Time } from "lightweight-charts";

import {
  buildChartDataFromCandles,
  getMockChartData,
  type ChartDataSet,
  type Timeframe
} from "./mock-market-data";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://ai-forex-signals.onrender.com";

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

export type MarketSearchResult = {
  epic: string;
  instrumentName?: string;
  marketName?: string;
  expiry?: string;
};

export type BackendCandle = {
  epic?: string | null;
  symbol: string;
  timeframe: string;
  resolution?: string | null;
  provider?: string | null;
  opened_at: string;
  open: number | string;
  high: number | string;
  low: number | string;
  close: number | string;
  volume?: number | string | null;
};

export type LiveChartLoadResult = {
  chartData: ChartDataSet;
  dataSource: "ig" | "mock";
  epic?: string;
  error?: string;
};

const resolutionByTimeframe: Record<Timeframe, string> = {
  "5m": "MINUTE_5",
  "15m": "MINUTE_15",
  "1h": "HOUR",
  "4h": "HOUR_4",
  "1d": "DAY"
};

export async function loadChartData(symbol: string, timeframe: Timeframe): Promise<LiveChartLoadResult> {
  try {
    const epic = await resolveMarketEpic(symbol);
    const backendCandles = await fetchCandles(epic, resolutionByTimeframe[timeframe], 300);
    const candles = backendCandles.map(toChartCandle).sort((left, right) => Number(left.time) - Number(right.time));

    if (candles.length === 0) {
      throw new Error("Backend returned no candles");
    }

    return {
      chartData: buildChartDataFromCandles(symbol, timeframe, candles),
      dataSource: "ig",
      epic
    };
  } catch (error) {
    return {
      chartData: getMockChartData(symbol, timeframe),
      dataSource: "mock",
      error: error instanceof Error ? error.message : "Unable to load IG candles"
    };
  }
}

export async function resolveMarketEpic(symbol: string): Promise<string> {
  const base = symbol.slice(0, 3);
  const quote = symbol.slice(3, 6);
  const queries = [`${base}/${quote}`, symbol];

  for (const query of queries) {
    const markets = await searchMarkets(query);
    const market = chooseMarket(symbol, markets);
    if (market?.epic) {
      return market.epic;
    }
  }

  throw new Error(`No IG market found for ${symbol}`);
}

export async function searchMarkets(query: string): Promise<MarketSearchResult[]> {
  const response = await fetch(`${API_BASE_URL}/api/markets/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error(`Market search failed with HTTP ${response.status}`);
  }

  const payload = (await response.json()) as { markets?: MarketSearchResult[] };
  return payload.markets ?? [];
}

export async function fetchCandles(epic: string, resolution: string, limit: number): Promise<BackendCandle[]> {
  const params = new URLSearchParams({
    epic,
    resolution,
    limit: String(limit)
  });
  const response = await fetch(`${API_BASE_URL}/api/candles?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Candle fetch failed with HTTP ${response.status}`);
  }

  return response.json();
}

function chooseMarket(symbol: string, markets: MarketSearchResult[]): MarketSearchResult | undefined {
  const compactSymbol = symbol.toUpperCase();
  const slashSymbol = `${symbol.slice(0, 3)}/${symbol.slice(3, 6)}`.toUpperCase();

  return (
    markets.find((market) => normalizeMarketName(market).includes(slashSymbol)) ??
    markets.find((market) => normalizeMarketName(market).includes(compactSymbol)) ??
    markets[0]
  );
}

function normalizeMarketName(market: MarketSearchResult): string {
  return [market.instrumentName, market.marketName, market.epic].filter(Boolean).join(" ").toUpperCase();
}

function toChartCandle(candle: BackendCandle): CandlestickData {
  return {
    time: Math.floor(new Date(candle.opened_at).getTime() / 1000) as Time,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close)
  };
}
