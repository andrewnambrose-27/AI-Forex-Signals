"use client";

import { Activity, BarChart3, History, KeyRound, ListPlus, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { scoreSignal, type Signal } from "@/lib/api";
import { ChartPanel } from "./chart-panel";
import { SignalPanel } from "./signal-panel";

const watchlist = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"];
const history = [
  { symbol: "EURUSD", direction: "BUY", score: 72, time: "09:30" },
  { symbol: "USDJPY", direction: "SELL", score: 61, time: "08:45" },
  { symbol: "GBPUSD", direction: "BUY", score: 58, time: "08:10" }
];

export function DashboardShell() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState("1h");
  const [signal, setSignal] = useState<Signal | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleScore() {
    setIsLoading(true);
    try {
      setSignal(await scoreSignal(symbol, timeframe));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Activity size={22} />
          AI Forex Signals
        </div>
        <nav className="nav-list">
          <div className="nav-item active">
            <BarChart3 size={18} /> Dashboard
          </div>
          <div className="nav-item">
            <ListPlus size={18} /> Watchlist
          </div>
          <div className="nav-item">
            <ShieldAlert size={18} /> Risk Filters
          </div>
          <div className="nav-item">
            <History size={18} /> History
          </div>
          <div className="nav-item">
            <KeyRound size={18} /> API Keys
          </div>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>Signal Dashboard</h1>
            <p>Signal-only analysis. This app does not place or execute live trades.</p>
          </div>
          <div className="toolbar">
            <select className="select" value={symbol} onChange={(event) => setSymbol(event.target.value)} aria-label="Forex pair">
              {watchlist.map((pair) => (
                <option key={pair} value={pair}>
                  {pair}
                </option>
              ))}
            </select>
            <select className="select" value={timeframe} onChange={(event) => setTimeframe(event.target.value)} aria-label="Timeframe">
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
            <button className="button" onClick={handleScore} disabled={isLoading}>
              <Activity size={18} />
              {isLoading ? "Scoring" : "Score"}
            </button>
          </div>
        </header>

        <div className="grid">
          <ChartPanel symbol={symbol} timeframe={timeframe} />
          <div className="stack">
            <SignalPanel signal={signal} symbol={symbol} timeframe={timeframe} />
            <section className="panel">
              <h2>Watchlist</h2>
              {watchlist.map((pair) => (
                <div className="watch-row" key={pair}>
                  <strong>{pair}</strong>
                  <span className="badge">Active</span>
                </div>
              ))}
            </section>
            <section className="panel">
              <h2>Signal History</h2>
              {history.map((item) => (
                <div className="history-row" key={`${item.symbol}-${item.time}`}>
                  <span>
                    <strong>{item.symbol}</strong> <span className="muted">{item.time}</span>
                  </span>
                  <span className="badge buy">
                    {item.direction} {item.score}
                  </span>
                </div>
              ))}
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
