import type { CandlestickData, LineData, SeriesMarker, Time } from "lightweight-charts";

export type Timeframe = "5m" | "15m" | "1h" | "4h" | "1d";
export type SignalDirection = "BUY" | "SELL" | "WAIT";

export type ChartSignal = {
  id: string;
  time: Time;
  direction: Exclude<SignalDirection, "WAIT">;
  score: number;
  price: number;
  reason: string;
};

export type ChartDataSet = {
  candles: CandlestickData[];
  ema20: LineData[];
  ema50: LineData[];
  ema200: LineData[];
  markers: SeriesMarker<Time>[];
  signals: ChartSignal[];
  ema200WarmingUp: boolean;
};

export const EMA_200_READY_CANDLES = 220;

export type LiveCandleUpdate = CandlestickData & {
  isClosed: boolean;
};

const timeframeSeconds: Record<Timeframe, number> = {
  "5m": 300,
  "15m": 900,
  "1h": 3600,
  "4h": 14400,
  "1d": 86400
};

const pairBasePrice: Record<string, number> = {
  EURUSD: 1.083,
  GBPUSD: 1.272,
  USDJPY: 157.6,
  AUDUSD: 0.664,
  USDCAD: 1.368,
  USDCHF: 0.895
};

function seededNoise(seed: number) {
  const value = Math.sin(seed * 999.91) * 10000;
  return value - Math.floor(value);
}

export function calculateEma(candles: CandlestickData[], period: number): LineData[] {
  const multiplier = 2 / (period + 1);
  let ema = Number(candles[0]?.close ?? 0);

  return candles.map((candle, index) => {
    const close = Number(candle.close);
    ema = index === 0 ? close : close * multiplier + ema * (1 - multiplier);
    return {
      time: candle.time,
      value: Number(ema.toFixed(5))
    };
  });
}

export function getMockChartData(symbol: string, timeframe: Timeframe): ChartDataSet {
  const basePrice = pairBasePrice[symbol] ?? 1.1;
  const step = timeframeSeconds[timeframe];
  const pointCount = 260;
  const startTime = 1717200000 - pointCount * step;
  const pipSize = symbol.endsWith("JPY") ? 0.035 : 0.00035;
  const candles: CandlestickData[] = [];

  let previousClose = basePrice;

  for (let index = 0; index < pointCount; index += 1) {
    const time = (startTime + index * step) as Time;
    const wave = Math.sin(index / 9) * pipSize * 7 + Math.cos(index / 17) * pipSize * 5;
    const drift = (index - pointCount / 2) * pipSize * 0.015;
    const noise = (seededNoise(index + symbol.length + step) - 0.5) * pipSize * 5;
    const open = previousClose;
    const close = basePrice + wave + drift + noise;
    const high = Math.max(open, close) + pipSize * (2 + seededNoise(index + 17) * 5);
    const low = Math.min(open, close) - pipSize * (2 + seededNoise(index + 31) * 5);

    candles.push({
      time,
      open: Number(open.toFixed(5)),
      high: Number(high.toFixed(5)),
      low: Number(low.toFixed(5)),
      close: Number(close.toFixed(5))
    });

    previousClose = close;
  }

  return {
    candles,
    ema20: calculateEma(candles, 20),
    ema50: calculateEma(candles, 50),
    ema200: calculateEma(candles, 200),
    markers: [],
    signals: [],
    ema200WarmingUp: false
  };
}

export function buildChartDataFromCandles(symbol: string, timeframe: Timeframe, candles: CandlestickData[]): ChartDataSet {
  const ema20 = calculateEma(candles, 20);
  const ema50 = calculateEma(candles, 50);
  const ema200WarmingUp = candles.length < EMA_200_READY_CANDLES;
  const ema200 = ema200WarmingUp ? [] : calculateEma(candles, 200);
  const lastCandle = candles[candles.length - 1];
  const lastEma20 = Number(ema20[ema20.length - 1]?.value ?? lastCandle.close);
  const direction = Number(lastCandle.close) >= lastEma20 ? "BUY" : "SELL";
  const score = direction === "BUY" ? 64 : 58;
  const signal: ChartSignal = {
    id: "latest-backend-candle",
    time: lastCandle.time,
    direction,
    score,
    price: Number(lastCandle.close),
    reason: `Latest IG ${timeframe} candle is ${direction === "BUY" ? "above" : "below"} EMA 20.`
  };

  return {
    candles,
    ema20,
    ema50,
    ema200,
    markers: [
      {
        time: signal.time,
        position: direction === "BUY" ? "belowBar" : "aboveBar",
        color: direction === "BUY" ? "#22c55e" : "#fb7185",
        shape: direction === "BUY" ? "arrowUp" : "arrowDown",
        text: `${direction} ${score}`
      }
    ],
    signals: [signal],
    ema200WarmingUp
  };
}

export function updateChartDataWithLivePrice(dataSet: ChartDataSet, symbol: string, timeframe: Timeframe, price: number): ChartDataSet {
  const candles = [...dataSet.candles];
  const latest = candles[candles.length - 1];
  if (!latest) {
    return dataSet;
  }

  candles[candles.length - 1] = {
    ...latest,
    high: Math.max(Number(latest.high), price),
    low: Math.min(Number(latest.low), price),
    close: Number(price.toFixed(symbol.endsWith("JPY") ? 3 : 5))
  };

  return {
    ...dataSet,
    candles
  };
}

export function applyStreamedCandleUpdate(dataSet: ChartDataSet, symbol: string, timeframe: Timeframe, update: LiveCandleUpdate): ChartDataSet {
  const candles = [...dataSet.candles];
  const updateTime = Number(update.time);
  const existingIndex = candles.findIndex((candle) => Number(candle.time) === updateTime);
  const nextCandle: CandlestickData = {
    time: update.time,
    open: update.open,
    high: update.high,
    low: update.low,
    close: update.close
  };

  if (existingIndex >= 0) {
    candles[existingIndex] = nextCandle;
  } else {
    candles.push(nextCandle);
    candles.sort((left, right) => Number(left.time) - Number(right.time));
  }

  if (update.isClosed) {
    return buildChartDataFromCandles(symbol, timeframe, candles);
  }

  return {
    ...dataSet,
    candles
  };
}

export function getLatestSignal(symbol: string, timeframe: Timeframe, dataSet: ChartDataSet) {
  const latest = dataSet.signals[dataSet.signals.length - 1];
  const lastClose = Number(dataSet.candles[dataSet.candles.length - 1]?.close ?? 0);
  const ema20 = Number(dataSet.ema20[dataSet.ema20.length - 1]?.value ?? 0);
  const ema50 = Number(dataSet.ema50[dataSet.ema50.length - 1]?.value ?? 0);
  const ema200 = Number(dataSet.ema200[dataSet.ema200.length - 1]?.value ?? 0);
  const trendAligned = ema20 > ema50 && ema50 > ema200;
  const hasEnoughCandles = dataSet.candles.length >= EMA_200_READY_CANDLES;

  if (!hasEnoughCandles) {
    return {
      symbol,
      timeframe,
      direction: "WAIT" as const,
      score: 0,
      price: lastClose,
      reasons: [`Loaded ${dataSet.candles.length} closed candles. Waiting for at least ${EMA_200_READY_CANDLES} before scoring.`],
      failedFilters: ["Not enough candle history", "EMA 200 warming up"]
    };
  }

  return {
    symbol,
    timeframe,
    direction: latest?.direction ?? "WAIT",
    score: latest?.score ?? 0,
    price: lastClose,
    reasons: [
      latest?.reason ?? "Waiting for a clean signal setup.",
      `Last close ${lastClose.toFixed(symbol.endsWith("JPY") ? 3 : 5)} versus EMA 20 ${ema20.toFixed(symbol.endsWith("JPY") ? 3 : 5)}.`,
      trendAligned ? "EMA stack is bullish across 20, 50, and 200." : "EMA stack is mixed, so conviction is capped."
    ],
    failedFilters: trendAligned ? ["High-impact news filter pending"] : ["EMA trend alignment", "High-impact news filter pending"]
  };
}
