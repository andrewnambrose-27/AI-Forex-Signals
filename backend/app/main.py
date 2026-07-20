from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, backtest, calendar, candles, health, ig, market_structure, signals, streaming, trend_lines, watchlist, zones
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ig.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(signals.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(market_structure.router, prefix="/api")
app.include_router(zones.router, prefix="/api")
app.include_router(trend_lines.router, prefix="/api")
app.include_router(streaming.router)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(candles.router, prefix=settings.api_v1_prefix)
app.include_router(signals.router, prefix=settings.api_v1_prefix)
app.include_router(watchlist.router, prefix=settings.api_v1_prefix)
