import type { Signal } from "@/lib/api";

export function SignalPanel({
  signal,
  symbol,
  timeframe
}: {
  signal: Signal | null;
  symbol: string;
  timeframe: string;
}) {
  const activeSignal =
    signal ??
    ({
      symbol,
      timeframe,
      direction: "WAIT",
      score: 0,
      rationale: "Run the signal engine to generate the latest score.",
      risk_flags: ["risk filters pending"],
      news_flags: ["news filters pending"]
    } satisfies Signal);

  return (
    <section className="panel">
      <h2>Signal Score</h2>
      <div className="score">{activeSignal.score}</div>
      <div className="signal-row">
        <span className="muted">Pair</span>
        <strong>{activeSignal.symbol}</strong>
      </div>
      <div className="signal-row">
        <span className="muted">Timeframe</span>
        <strong>{activeSignal.timeframe}</strong>
      </div>
      <div className="signal-row">
        <span className="muted">Direction</span>
        <span className="badge buy">{activeSignal.direction}</span>
      </div>
      <p>{activeSignal.rationale}</p>
      <div className="signal-row">
        <span className="muted">Risk</span>
        <span className="badge warn">{activeSignal.risk_flags.join(", ") || "clear"}</span>
      </div>
      <div className="signal-row">
        <span className="muted">News</span>
        <span className="badge warn">{activeSignal.news_flags.join(", ") || "clear"}</span>
      </div>
    </section>
  );
}
