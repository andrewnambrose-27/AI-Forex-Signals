"use client";

import {
  ColorType,
  CrosshairMode,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type Time
} from "lightweight-charts";
import { useEffect, useRef } from "react";

type ChartPanelProps = {
  symbol: string;
  timeframe: string;
  dataSource: "ig" | "mock";
  epic?: string;
  candles: CandlestickData[];
  ema20: LineData[];
  ema50: LineData[];
  ema200: LineData[];
  ema200WarmingUp: boolean;
  markers: SeriesMarker<Time>[];
  requestedCandles?: number;
  loadedCandles?: number;
  candleWarning?: string | null;
};

export function ChartPanel({
  symbol,
  timeframe,
  dataSource,
  epic,
  candles,
  ema20,
  ema50,
  ema200,
  ema200WarmingUp,
  markers,
  requestedCandles,
  loadedCandles,
  candleWarning
}: ChartPanelProps) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const previousViewportKeyRef = useRef("");
  const candleDateRange = formatCandleDateRange(candles);

  useEffect(() => {
    if (!chartContainerRef.current) {
      return;
    }

    const container = chartContainerRef.current;
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 560,
      layout: {
        background: { type: ColorType.Solid, color: "#080b12" },
        textColor: "#9ca3af"
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" }
      },
      crosshair: {
        mode: CrosshairMode.Normal
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.22)"
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.22)",
        timeVisible: true,
        secondsVisible: false
      }
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#f43f5e",
      borderUpColor: "#22c55e",
      borderDownColor: "#f43f5e",
      wickUpColor: "#86efac",
      wickDownColor: "#fda4af"
    });

    const ema20Series = chart.addLineSeries({ color: "#38bdf8", lineWidth: 2, priceLineVisible: false });
    const ema50Series = chart.addLineSeries({ color: "#f59e0b", lineWidth: 2, priceLineVisible: false });
    const ema200Series = chart.addLineSeries({ color: "#a78bfa", lineWidth: 2, priceLineVisible: false });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    ema20Ref.current = ema20Series;
    ema50Ref.current = ema50Series;
    ema200Ref.current = ema200Series;

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: Math.floor(entry.contentRect.width) });
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
    };
  }, []);

  useEffect(() => {
    candleSeriesRef.current?.setData(candles);
    candleSeriesRef.current?.setMarkers(markers);
    ema20Ref.current?.setData(ema20);
    ema50Ref.current?.setData(ema50);
    ema200Ref.current?.setData(ema200);
    const viewportKey = `${dataSource}:${symbol}:${timeframe}:${epic ?? ""}`;
    if (previousViewportKeyRef.current !== viewportKey && candles.length > 0) {
      const latestIndex = candles.length - 1;
      const visibleBars = Math.min(160, candles.length);
      chartRef.current?.timeScale().setVisibleLogicalRange({
        from: Math.max(0, latestIndex - visibleBars + 1),
        to: latestIndex + 8
      });
      previousViewportKeyRef.current = viewportKey;
    }
  }, [dataSource, epic, symbol, timeframe, candles, ema20, ema50, ema200, markers]);

  return (
    <section className="chart-panel">
      <div className="chart-header">
        <div>
          <span className="eyebrow">{dataSource === "ig" ? "IG demo candles" : "Mock fallback"}</span>
          <h2>{symbol}</h2>
        </div>
        <div className="chart-meta">
          <span>{timeframe}</span>
          {epic ? <span>{epic}</span> : null}
          <span>{loadedCandles ?? candles.length} candles loaded{requestedCandles ? ` / ${requestedCandles} requested` : ""}</span>
          {candleDateRange ? <span>{candleDateRange}</span> : null}
          <span>{ema200WarmingUp ? "EMA 200 warming up" : "EMA 20 / 50 / 200"}</span>
        </div>
      </div>
      {candleWarning ? <div className="chart-warning">{candleWarning}</div> : null}
      <div className="chart-canvas" ref={chartContainerRef} />
      <div className="legend">
        <span>
          <i className="legend-dot ema20" /> EMA 20
        </span>
        <span>
          <i className="legend-dot ema50" /> EMA 50
        </span>
        <span>
          <i className="legend-dot ema200" /> EMA 200{ema200WarmingUp ? " warming up" : ""}
        </span>
        <span>
          <i className="legend-dot signal" /> Signal markers
        </span>
      </div>
    </section>
  );
}

function formatCandleDateRange(candles: CandlestickData[]): string | null {
  const first = candles[0]?.time;
  const last = candles[candles.length - 1]?.time;
  if (typeof first !== "number" || typeof last !== "number") {
    return null;
  }

  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
  return `${dateFormatter.format(new Date(first * 1000))} - ${dateFormatter.format(new Date(last * 1000))}`;
}
