"use client";

import { Activity, BarChart3, History, ListPlus, Radar, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchLiveQuote, loadChartData, type LiveChartLoadResult, type LiveQuote } from "@/lib/api";
import { getLatestSignal, getMockChartData, updateChartDataWithLivePrice, type Timeframe } from "@/lib/mock-market-data";
import { ChartPanel } from "./chart-panel";
import { SignalPanel } from "./signal-panel";

const watchlist = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"];
const timeframes: Timeframe[] = ["5m", "15m", "1h", "4h", "1d"];
const autoRefreshMsByTimeframe: Record<Timeframe, number> = {
  "5m": 30000,
  "15m": 45000,
  "1h": 60000,
  "4h": 120000,
  "1d": 300000
};
const quoteRefreshMs = 5000;

export function DashboardShell() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [refreshCount, setRefreshCount] = useState(0);
  const [chartResult, setChartResult] = useState<LiveChartLoadResult>(() => ({
    chartData: getMockChartData("EURUSD", "1h"),
    dataSource: "mock"
  }));
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [latestQuote, setLatestQuote] = useState<LiveQuote | null>(null);
  const [quoteUpdatedAt, setQuoteUpdatedAt] = useState<Date | null>(null);
  const chartData = chartResult.chartData;
  const latestSignal = useMemo(() => getLatestSignal(symbol, timeframe, chartData), [symbol, timeframe, chartData]);

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
    if (chartResult.dataSource !== "ig") {
      return;
    }

    let isCancelled = false;

    async function refreshQuote() {
      try {
        const quote = await fetchLiveQuote(symbol, chartResult.epic);
        if (isCancelled) {
          return;
        }
        setLatestQuote(quote);
        setQuoteUpdatedAt(new Date());
        setChartResult((current) => {
          if (current.dataSource !== "ig") {
            return current;
          }
          return {
            ...current,
            epic: current.epic ?? quote.epic,
            chartData: updateChartDataWithLivePrice(current.chartData, symbol, timeframe, quote.mid)
          };
        });
      } catch {
        // Historical candle data remains visible if a transient quote poll fails.
      }
    }

    refreshQuote();
    const intervalId = window.setInterval(refreshQuote, quoteRefreshMs);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [chartResult.dataSource, chartResult.epic, symbol, timeframe]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setRefreshCount((value) => value + 1);
    }, autoRefreshMsByTimeframe[timeframe]);

    return () => window.clearInterval(intervalId);
  }, [timeframe]);

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
          <span>{chartResult.dataSource === "ig" ? "Connected to IG demo candles" : "Using mock fallback data"}</span>
          {latestQuote ? <span>Live mid {latestQuote.mid.toFixed(symbol.endsWith("JPY") ? 3 : 5)}</span> : null}
          {latestQuote ? <span>Bid {latestQuote.bid.toFixed(symbol.endsWith("JPY") ? 3 : 5)} / Ask {latestQuote.offer.toFixed(symbol.endsWith("JPY") ? 3 : 5)}</span> : null}
          {quoteUpdatedAt ? <span>Quote {quoteUpdatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> : null}
          <span>Auto-refresh {Math.round(autoRefreshMsByTimeframe[timeframe] / 1000)}s</span>
          {lastUpdatedAt ? <span>Updated {lastUpdatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> : null}
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
            markers={chartData.markers}
          />
          <SignalPanel signal={latestSignal} />
        </div>
      </main>
    </div>
  );
}
