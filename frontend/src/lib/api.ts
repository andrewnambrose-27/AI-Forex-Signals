import type { CandlestickData, Time } from "lightweight-charts";

import {
  buildChartDataFromCandles,
  getMockChartData,
  type ChartDataSet,
  type Timeframe
} from "./mock-market-data";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://ai-forex-signals.onrender.com";
const CANDLE_WARNING_TOLERANCE = 10;

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
  bid?: number | null;
  offer?: number | null;
  marketStatus?: string;
  updateTime?: string;
  updateTimeUTC?: string;
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

export type CandleBootstrap = {
  epic: string;
  resolution: string;
  requested_count: number;
  loaded_count: number;
  candles: BackendCandle[];
  warning?: string | null;
  dropped_incomplete_current_candle?: boolean;
};

export type LiveChartLoadResult = {
  chartData: ChartDataSet;
  dataSource: "ig" | "mock";
  epic?: string;
  error?: string;
  requestedCandles?: number;
  loadedCandles?: number;
  candleWarning?: string | null;
  droppedIncompleteCurrentCandle?: boolean;
};

export type LiveQuote = {
  epic: string;
  bid: number;
  offer: number;
  mid: number;
  marketStatus?: string;
  updateTime?: string;
};

export type StreamStatus = "idle" | "historical_loaded" | "connected" | "reconnecting" | "failed";

export type StreamCandleUpdate = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  isClosed: boolean;
};

export type PriceStreamMessage =
  | {
      type: "stream_status";
      status: Exclude<StreamStatus, "idle" | "historical_loaded" | "reconnecting">;
      symbol: string;
      timeframe: Timeframe;
      message?: string;
    }
  | {
      type: "candle_update";
      symbol: string;
      timeframe: Timeframe;
      candle: StreamCandleUpdate;
      bid?: number;
      offer?: number;
      mid?: number;
    };

export type BacktestRequest = {
  epic: string;
  pair: string;
  timeframe: Timeframe;
  limit: number;
  spread_points: number;
  slippage_points: number;
  minimum_score: number;
};

export type BacktestTrade = {
  strategy: string;
  direction: "BUY" | "SELL";
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  take_profit: number;
  r_multiple: number;
  hold_minutes: number;
  session: string;
  news_filtered_period: boolean;
};

export type BacktestResult = {
  pair: string;
  epic: string;
  timeframe: string;
  assumptions: Record<string, string | number>;
  metrics: {
    win_rate: number;
    average_r: number;
    max_drawdown: number;
    profit_factor: number;
    number_of_trades: number;
    average_hold_time_minutes: number;
    performance_by_session: Record<string, { trades: number; average_r: number; total_r: number }>;
    performance_around_news_filtered_periods: { trades: number; average_r: number; total_r?: number };
  };
  trades: BacktestTrade[];
  skipped_signals: number;
  notes: string[];
};

const resolutionByTimeframe: Record<Timeframe, string> = {
  "5m": "MINUTE_5",
  "15m": "MINUTE_15",
  "1h": "HOUR",
  "4h": "HOUR_4",
  "1d": "DAY"
};

export const defaultCandleCountByTimeframe: Record<Timeframe, number> = {
  "5m": 1000,
  "15m": 1000,
  "1h": 750,
  "4h": 500,
  "1d": 400
};

export async function loadChartData(symbol: string, timeframe: Timeframe): Promise<LiveChartLoadResult> {
  try {
    const epic = await resolveMarketEpic(symbol);
    const candleBootstrap = await fetchCandles(epic, resolutionByTimeframe[timeframe], defaultCandleCountByTimeframe[timeframe]);
    const candles = candleBootstrap.candles.map(toChartCandle).sort((left, right) => Number(left.time) - Number(right.time));

    if (candles.length === 0) {
      throw new Error("Backend returned no candles");
    }

    return {
      chartData: buildChartDataFromCandles(symbol, timeframe, candles),
      dataSource: "ig",
      epic,
      requestedCandles: candleBootstrap.requested_count,
      loadedCandles: candleBootstrap.loaded_count,
      candleWarning: candleBootstrap.warning,
      droppedIncompleteCurrentCandle: candleBootstrap.dropped_incomplete_current_candle
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

export async function fetchCandles(epic: string, resolution: string, limit: number): Promise<CandleBootstrap> {
  const params = new URLSearchParams({
    epic,
    resolution,
    limit: String(limit)
  });
  const response = await fetch(`${API_BASE_URL}/api/candles?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Candle fetch failed with HTTP ${response.status}`);
  }

  const payload = await response.json();
  if (Array.isArray(payload)) {
    return {
      epic,
      resolution,
      requested_count: limit,
      loaded_count: payload.length,
      candles: payload,
      warning: payload.length + CANDLE_WARNING_TOLERANCE < limit ? `Loaded ${payload.length} candles, fewer than the ${limit} requested.` : null,
      dropped_incomplete_current_candle: false
    };
  }

  return payload;
}

export function getPriceWebSocketUrl(symbol: string, timeframe: Timeframe, epic?: string): string {
  const apiUrl = new URL(API_BASE_URL);
  apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  apiUrl.pathname = "/ws/prices";
  apiUrl.search = "";
  apiUrl.searchParams.set("symbol", symbol);
  apiUrl.searchParams.set("timeframe", timeframe);
  if (epic) {
    apiUrl.searchParams.set("epic", epic);
  }
  return apiUrl.toString();
}

export async function fetchLiveQuote(symbol: string, epic?: string): Promise<LiveQuote> {
  const markets = await searchMarkets(`${symbol.slice(0, 3)}/${symbol.slice(3, 6)}`);
  const market = (epic ? markets.find((item) => item.epic === epic) : undefined) ?? chooseMarket(symbol, markets);
  if (!market?.epic || market.bid == null || market.offer == null) {
    throw new Error(`No live quote available for ${symbol}`);
  }

  const bid = Number(market.bid);
  const offer = Number(market.offer);
  return {
    epic: market.epic,
    bid,
    offer,
    mid: (bid + offer) / 2,
    marketStatus: market.marketStatus,
    updateTime: market.updateTimeUTC ?? market.updateTime
  };
}

export async function runBacktest(payload: BacktestRequest): Promise<BacktestResult> {
  const response = await fetch(`${API_BASE_URL}/api/backtest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Backtest failed with HTTP ${response.status}`);
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
