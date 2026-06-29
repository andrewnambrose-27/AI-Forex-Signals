import { AlertTriangle, CheckCircle2, TrendingDown, TrendingUp } from "lucide-react";

import type { SignalDirection, Timeframe } from "@/lib/mock-market-data";

type LatestSignal = {
  symbol: string;
  timeframe: Timeframe;
  direction: SignalDirection;
  score: number;
  price: number;
  reasons: string[];
  failedFilters: string[];
};

export function SignalPanel({ signal }: { signal: LatestSignal }) {
  const isSell = signal.direction === "SELL";
  const DirectionIcon = isSell ? TrendingDown : TrendingUp;

  return (
    <aside className="signal-sidebar">
      <section className="signal-card score-card">
        <div className="score-topline">
          <span className="eyebrow">Latest signal</span>
          <span className={`direction-pill ${signal.direction.toLowerCase()}`}>
            <DirectionIcon size={15} />
            {signal.direction}
          </span>
        </div>
        <div className="score-readout">
          <strong>{signal.score}</strong>
          <span>/100</span>
        </div>
        <div className="score-bar">
          <span style={{ width: `${signal.score}%` }} />
        </div>
        <div className="signal-pair-row">
          <span>{signal.symbol}</span>
          <span>{signal.timeframe}</span>
          <span>{signal.price.toFixed(signal.symbol.endsWith("JPY") ? 3 : 5)}</span>
        </div>
      </section>

      <section className="signal-card">
        <h2>Reasons</h2>
        <div className="reason-list">
          {signal.reasons.map((reason) => (
            <div className="reason-item" key={reason}>
              <CheckCircle2 size={17} />
              <span>{reason}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="signal-card">
        <h2>Failed Filters</h2>
        <div className="reason-list">
          {signal.failedFilters.map((filter) => (
            <div className="reason-item failed" key={filter}>
              <AlertTriangle size={17} />
              <span>{filter}</span>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
