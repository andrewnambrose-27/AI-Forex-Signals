import { AlertTriangle, CheckCircle2, TrendingDown, TrendingUp } from "lucide-react";

import type { SignalDirection, Timeframe } from "@/lib/mock-market-data";
import type { MultiTimeframeAnalysis, TimeframeState } from "@/lib/api";

type LatestSignal = {
  symbol: string;
  timeframe: Timeframe;
  direction: SignalDirection;
  score: number;
  price: number;
  reasons: string[];
  failedFilters: string[];
};

export function SignalPanel({ signal, multiTimeframe }: { signal: LatestSignal; multiTimeframe?: MultiTimeframeAnalysis | null }) {
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
        <h2>Multi-timeframe view</h2>
        {multiTimeframe ? (
          <div className="multi-timeframe-view">
            {[multiTimeframe.entry_state, multiTimeframe.confirmation_state, multiTimeframe.higher_timeframe_state]
              .filter((state): state is TimeframeState => state !== null)
              .map((state) => (
                <div className="timeframe-state" key={`${state.role}-${state.timeframe}`}>
                  <div>
                    <strong>{state.timeframe}</strong>
                    <span>{roleLabel(state.role)}</span>
                  </div>
                  <span className={`timeframe-direction ${state.direction}`}>{state.direction.replace("_", " ")}</span>
                  <small>EMA {state.ema_alignment} · structure {state.market_structure} · ADX {state.adx?.toFixed(1) ?? "—"}</small>
                </div>
              ))}
            <div className={`timeframe-overall ${multiTimeframe.result}`}>
              <span>Overall</span>
              <strong>{multiTimeframe.overall_summary}</strong>
              <small>{multiTimeframe.result}{multiTimeframe.score_penalty ? ` · −${multiTimeframe.score_penalty} score` : ""}</small>
            </div>
            <p>{multiTimeframe.reasons[0]}</p>
          </div>
        ) : (
          <div className="reason-item"><span>Multi-timeframe analysis unavailable.</span></div>
        )}
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

function roleLabel(role: TimeframeState["role"]): string {
  return role === "entry" ? "Entry" : role === "confirmation" ? "Confirmation" : "Directional bias";
}
