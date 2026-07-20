"use client";

import { Activity, BarChart3, History, ListPlus, Radar, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { CandlestickData, Time } from "lightweight-charts";

import {
  getPriceWebSocketUrl,
  loadChartData,
  type LiveChartLoadResult,
  type LiveQuote,
  type PriceStreamMessage,
  type StreamStatus
} from "@/lib/api";
import { applyStreamedCandleUpdate, getLatestSignal, getUnavailableChartData, type LiveCandleUpdate, type Timeframe } from "@/lib/mock-market-data";
import { ChartPanel } from "./chart-panel";
import { SignalPanel } from "./signal-panel";

const watchlist = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"];
const timeframes: Timeframe[] = ["5m", "15m", "1h", "4h", "1d"];
const maxStreamReconnectAttempts = 8;

export function DashboardShell() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [refreshCount, setRefreshCount] = useState(0);
  const [chartResult, setChartResult] = useState<LiveChartLoadResult>(() => ({
    chartData: getUnavailableChartData(),
    dataSource: "unavailable"
  }));
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [latestQuote, setLatestQuote] = useState<LiveQuote | null>(null);
  const [quoteUpdatedAt, setQuoteUpdatedAt] = useState<Date | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [streamMessage, setStreamMessage] = useState<string | null>(null);
  const [livePreviewCandle, setLivePreviewCandle] = useState<CandlestickData | null>(null);
  const chartData = chartResult.chartData;
  const latestSignal = useMemo(() => {
    if (chartResult.dataSource !== "ig") {
      return unavailableSignal(symbol, timeframe, chartData);
    }
    return getLatestSignal(symbol, timeframe, chartData);
  }, [symbol, timeframe, chartData, chartResult.dataSource]);

  useEffect(() => {
    let isCancelled = false;
    setIsLoading(true);

    loadChartData(symbol, timeframe)
      .then((result) => {
        if (!isCancelled) {
          setChartResult(result);
          setLastUpdatedAt(new Date());
          setLatestQuote(null);
          setQuoteUpdatedAt(null);
          setLivePreviewCandle(null);
          setStreamMessage(null);
          setStreamStatus(result.dataSource === "ig" ? "historical_loaded" : "idle");
        }
      })
      .finally(() => {
        if (!isCancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [symbol, timeframe, refreshCount]);

  useEffect(() => {
    if (chartResult.dataSource !== "ig" || !chartResult.epic) {
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let retryCount = 0;
    let shouldReconnect = true;

    function connect() {
      setStreamStatus(retryCount === 0 ? "historical_loaded" : "reconnecting");
      socket = new WebSocket(getPriceWebSocketUrl(symbol, timeframe, chartResult.epic));

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as PriceStreamMessage;
        if (message.type === "stream_status") {
          setStreamStatus(message.status);
          setStreamMessage(message.message ?? null);
          if (message.status === "failed") {
            socket?.close();
          }
          return;
        }

        const streamedCandle: LiveCandleUpdate = {
          time: message.candle.time as Time,
          open: message.candle.open,
          high: message.candle.high,
          low: message.candle.low,
          close: message.candle.close,
          isClosed: message.candle.isClosed
        };
        retryCount = 0;
        setStreamStatus("connected");
        setStreamMessage(null);
        setLivePreviewCandle(streamedCandle);
        setChartResult((current) => ({
          ...current,
          chartData: applyStreamedCandleUpdate(current.chartData, symbol, timeframe, streamedCandle)
        }));
        if (message.mid != null && message.bid != null && message.offer != null) {
          setLatestQuote({
            epic: chartResult.epic ?? "",
            bid: message.bid,
            offer: message.offer,
            mid: message.mid,
            updateTime: new Date().toISOString()
          });
          setQuoteUpdatedAt(new Date());
        }
      };

      socket.onopen = () => {
        setStreamMessage(null);
      };

      socket.onclose = () => {
        if (!shouldReconnect) {
          return;
        }
        retryCount += 1;
        if (retryCount > maxStreamReconnectAttempts) {
          setStreamStatus("failed");
          setStreamMessage("Streaming failed after several reconnect attempts. Use Refresh for REST fallback.");
          return;
        }
        setStreamStatus("reconnecting");
        reconnectTimer = window.setTimeout(connect, Math.min(10000, 1000 * retryCount));
      };

      socket.onerror = () => {
        setStreamStatus("reconnecting");
      };
    }

    connect();

    return () => {
      shouldReconnect = false;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [chartResult.dataSource, chartResult.epic, symbol, timeframe]);

  return (
    <div className="terminal-shell">
      <aside className="sidebar">
        <div className="brand">
          <Radar size={23} />
          AI Forex Signals
        </div>
        <nav className="nav-list">
          <div className="nav-item active">
            <BarChart3 size={18} /> Chart
          </div>
          <div className="nav-item">
            <ListPlus size={18} /> Watchlist
          </div>
          <div className="nav-item">
            <ShieldAlert size={18} /> Risk
          </div>
          <Link className="nav-item" href="/backtest">
            <History size={18} /> History
          </Link>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="eyebrow">Private dashboard</span>
            <h1>Forex Signal Chart</h1>
          </div>
          <div className="toolbar">
            <select className="select" value={symbol} onChange={(event) => setSymbol(event.target.value)} aria-label="Forex pair">
              {watchlist.map((pair) => (
                <option key={pair} value={pair}>
                  {pair}
                </option>
              ))}
            </select>
            <div className="segmented-control" aria-label="Timeframe selector">
              {timeframes.map((option) => (
                <button
                  className={option === timeframe ? "active" : ""}
                  key={option}
                  onClick={() => setTimeframe(option)}
                  type="button"
                >
                  {option}
                </button>
              ))}
            </div>
            <button className="button" type="button" onClick={() => setRefreshCount((value) => value + 1)} disabled={isLoading}>
              <Activity size={18} />
              {isLoading ? "Loading" : "Refresh"}
            </button>
          </div>
        </header>

        <div className={`data-status ${chartResult.dataSource === "ig" ? "live" : "mock"}`}>
          <span>{chartResult.dataSource === "ig" ? "Connected to IG demo candles" : "Real IG candles unavailable"}</span>
          {chartResult.dataSource === "ig" ? <span>{streamStatusLabel(streamStatus)}</span> : null}
          {latestQuote ? <span>Live mid {latestQuote.mid.toFixed(symbol.endsWith("JPY") ? 3 : 5)}</span> : null}
          {latestQuote ? <span>Bid {latestQuote.bid.toFixed(symbol.endsWith("JPY") ? 3 : 5)} / Ask {latestQuote.offer.toFixed(symbol.endsWith("JPY") ? 3 : 5)}</span> : null}
          {quoteUpdatedAt ? <span>Quote {quoteUpdatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> : null}
          <span>REST refresh manual</span>
          <span>
            Candles {chartResult.loadedCandles ?? chartData.candles.length}
            {chartResult.requestedCandles ? ` / ${chartResult.requestedCandles}` : ""}
          </span>
          {chartResult.droppedIncompleteCurrentCandle ? <span>Current incomplete candle excluded</span> : null}
          {lastUpdatedAt ? <span>Updated {lastUpdatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> : null}
          {chartResult.candleWarning ? <span>{chartResult.candleWarning}</span> : null}
          {streamMessage ? <span>{streamMessage}</span> : null}
          {chartResult.error ? <span>{chartResult.error}</span> : null}
        </div>

        <div className="chart-layout">
          <ChartPanel
            symbol={symbol}
            timeframe={timeframe}
            dataSource={chartResult.dataSource}
            epic={chartResult.epic}
            candles={chartData.candles}
            ema20={chartData.ema20}
            ema50={chartData.ema50}
            ema200={chartData.ema200}
            ema200WarmingUp={chartData.ema200WarmingUp}
            markers={chartData.markers}
            requestedCandles={chartResult.requestedCandles}
            loadedCandles={chartResult.loadedCandles}
            candleWarning={chartResult.candleWarning}
            livePreviewCandle={livePreviewCandle}
            marketStructure={chartResult.marketStructure}
            zoneAnalysis={chartResult.zoneAnalysis}
            trendLineAnalysis={chartResult.trendLineAnalysis}
          />
          <SignalPanel signal={latestSignal} multiTimeframe={chartResult.multiTimeframeAnalysis} />
        </div>
      </main>
    </div>
  );
}

function streamStatusLabel(status: StreamStatus): string {
  const labels: Record<StreamStatus, string> = {
    idle: "Streaming idle",
    historical_loaded: "Historical loaded",
    connected: "Streaming connected",
    reconnecting: "Streaming reconnecting",
    failed: "Streaming failed"
  };
  return labels[status];
}

function unavailableSignal(symbol: string, timeframe: Timeframe, dataSet: { candles: CandlestickData[] }) {
  const lastClose = Number(dataSet.candles[dataSet.candles.length - 1]?.close ?? 0);
  return {
    symbol,
    timeframe,
    direction: "WAIT" as const,
    score: 0,
    price: lastClose,
    reasons: ["Signal unavailable while real IG candles are unavailable."],
    failedFilters: ["Real IG candles unavailable"]
  };
}
