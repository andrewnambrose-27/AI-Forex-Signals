"use client";

import { Activity, BarChart3, History, ListPlus, Radar, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { loadChartData, type LiveChartLoadResult } from "@/lib/api";
import { getLatestSignal, getMockChartData, type Timeframe } from "@/lib/mock-market-data";
import { ChartPanel } from "./chart-panel";
import { SignalPanel } from "./signal-panel";

const watchlist = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"];
const timeframes: Timeframe[] = ["5m", "15m", "1h", "4h", "1d"];

export function DashboardShell() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [refreshCount, setRefreshCount] = useState(0);
  const [chartResult, setChartResult] = useState<LiveChartLoadResult>(() => ({
    chartData: getMockChartData("EURUSD", "1h"),
    dataSource: "mock"
  }));
  const [isLoading, setIsLoading] = useState(false);
  const chartData = chartResult.chartData;
  const latestSignal = useMemo(() => getLatestSignal(symbol, timeframe, chartData), [symbol, timeframe, chartData]);

  useEffect(() => {
    let isCancelled = false;
    setIsLoading(true);

    loadChartData(symbol, timeframe)
      .then((result) => {
        if (!isCancelled) {
          setChartResult(result);
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
          <div className="nav-item">
            <History size={18} /> History
          </div>
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
