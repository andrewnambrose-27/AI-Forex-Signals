from app.schemas.signal import SignalRead, SignalRequest


def generate_signal(payload: SignalRequest) -> SignalRead:
    # Placeholder engine: replace with a tested strategy fed by stored candles and filters.
    symbol = payload.symbol.upper()
    base_score = 55
    risk_flags: list[str] = []
    news_flags: list[str] = []

    if payload.timeframe in {"1m", "5m"}:
        risk_flags.append("short_timeframe_noise")
        base_score -= 8

    direction = "BUY" if base_score >= 50 else "SELL"
    return SignalRead(
        symbol=symbol,
        timeframe=payload.timeframe,
        direction=direction,
        score=max(0, min(100, base_score)),
        rationale="Initial placeholder signal. No trades are placed by this application.",
        risk_flags=risk_flags,
        news_flags=news_flags,
    )
