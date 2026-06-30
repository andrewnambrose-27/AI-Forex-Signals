"use client";

import { Activity, BarChart3, History, Radar, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { runBacktest, type BacktestResult } from "@/lib/api";
import type { Timeframe } from "@/lib/mock-market-data";

const pairs = [
  { pair: "EURUSD", epic: "CS.D.EURUSD.MINI.IP" },
  { pair: "GBPUSD", epic: "CS.D.GBPUSD.MINI.IP" },
  { pair: "USDJPY", epic: "CS.D.USDJPY.MINI.IP" }
];
const timeframes: Timeframe[] = ["5m", "15m", "1h", "4h", "1d"];

export function BacktestShell() {
  const [pair, setPair] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [minimumScore, setMinimumScore] = useState(80);
  const [spread, setSpread] = useState(0.00008);
  const [slippage, setSlippage] = useState(0.00002);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const selectedEpic = pairs.find((item) => item.pair === pair)?.epic ?? pairs[0].epic;

  async function handleRun() {
    setIsRunning(true);
    setError(null);
    try {
      const backtest = await runBacktest({
        epic: selectedEpic,
        pair,
        timeframe,
        limit: 300,
        spread_points: spread,
        slippage_points: slippage,
        minimum_score: minimumScore
      });
      setResult(backtest);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Backtest failed");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="terminal-shell">
      <aside className="sidebar">
        <div className="brand">
          <Radar size={23} />
          AI Forex Signals
        </div>
        <nav className="nav-list">
          <Link className="nav-item" href="/">
            <BarChart3 size={18} /> Chart
          </Link>
          <div className="nav-item active">
            <History size={18} /> Backtest
          </div>
          <div className="nav-item">
            <ShieldAlert size={18} /> Risk
          </div>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="eyebrow">Strategy lab</span>
            <h1>Backtest</h1>
          </div>
          <button className="button" type="button" onClick={handleRun} disabled={isRunning}>
            <Activity size={18} />
            {isRunning ? "Running" : "Run Backtest"}
          </button>
        </header>

        <section className="backtest-grid">
          <div className="control-panel">
            <label>
              <span>Pair</span>
              <select className="select" value={pair} onChange={(event) => setPair(event.target.value)}>
                {pairs.map((item) => (
                  <option key={item.pair} value={item.pair}>
                    {item.pair}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Timeframe</span>
              <select className="select" value={timeframe} onChange={(event) => setTimeframe(event.target.value as Timeframe)}>
                {timeframes.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Minimum score</span>
              <input className="input" type="number" min={0} max={100} value={minimumScore} onChange={(event) => setMinimumScore(Number(event.target.value))} />
            </label>
            <label>
              <span>Spread</span>
              <input className="input" type="number" step="0.00001" min={0} value={spread} onChange={(event) => setSpread(Number(event.target.value))} />
            </label>
            <label>
              <span>Slippage</span>
              <input className="input" type="number" step="0.00001" min={0} value={slippage} onChange={(event) => setSlippage(Number(event.target.value))} />
            </label>
          </div>

          <div className="results-panel">
            {error ? <div className="data-status mock"><span>{error}</span></div> : null}
            {result ? <BacktestResults result={result} /> : <EmptyState />}
          </div>
        </section>
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="metric-grid">
      {["Win rate", "Average R", "Max drawdown", "Profit factor"].map((label) => (
        <div className="metric-card" key={label}>
          <span>{label}</span>
          <strong>-</strong>
        </div>
      ))}
    </div>
  );
}

function BacktestResults({ result }: { result: BacktestResult }) {
  const metrics = result.metrics;
  return (
    <div className="backtest-results">
      <div className="metric-grid">
        <Metric label="Win rate" value={`${metrics.win_rate}%`} />
        <Metric label="Average R" value={metrics.average_r.toFixed(2)} />
        <Metric label="Max drawdown" value={`${metrics.max_drawdown.toFixed(2)}R`} />
        <Metric label="Profit factor" value={metrics.profit_factor.toFixed(2)} />
        <Metric label="Trades" value={String(metrics.number_of_trades)} />
        <Metric label="Avg hold" value={`${metrics.average_hold_time_minutes.toFixed(0)}m`} />
      </div>

      <div className="table-panel">
        <h2>Session Performance</h2>
        <div className="session-grid">
          {Object.entries(metrics.performance_by_session).map(([session, values]) => (
            <div className="session-row" key={session}>
              <span>{session.replaceAll("_", " ")}</span>
              <strong>{values.total_r.toFixed(2)}R</strong>
              <em>{values.trades} trades</em>
            </div>
          ))}
        </div>
      </div>

      <div className="table-panel">
        <h2>Recent Trades</h2>
        <div className="trade-table">
          {result.trades.slice(-8).map((trade, index) => (
            <div className="trade-row" key={`${trade.entry_time}-${index}`}>
              <span>{trade.strategy.replaceAll("_", " ")}</span>
              <strong className={trade.r_multiple >= 0 ? "positive" : "negative"}>{trade.r_multiple.toFixed(2)}R</strong>
              <em>{trade.session.replaceAll("_", " ")}</em>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
