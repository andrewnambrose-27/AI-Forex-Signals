const candleHeights = [42, 58, 35, 64, 88, 73, 96, 68, 51, 79, 110, 94, 70, 84, 122, 104, 91, 76, 114, 132, 98, 83, 106, 124];

export function ChartPanel({ symbol, timeframe }: { symbol: string; timeframe: string }) {
  return (
    <section className="panel">
      <h2>{symbol} Candlestick Chart</h2>
      <div className="chart-frame">
        <div className="fake-chart" aria-label={`${symbol} ${timeframe} candlestick chart placeholder`}>
          {candleHeights.map((height, index) => (
            <div
              className={`candle ${index % 3 === 0 ? "sell" : "buy"}`}
              key={`${height}-${index}`}
              style={{ height }}
              title={`${symbol} ${timeframe}`}
            />
          ))}
        </div>
        <p className="muted">Ready for live and historical candles from the backend.</p>
      </div>
    </section>
  );
}
