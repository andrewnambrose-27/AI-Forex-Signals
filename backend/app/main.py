from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, candles, health, ig, signals, watchlist
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ig.router, prefix="/api")
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(candles.router, prefix=settings.api_v1_prefix)
app.include_router(signals.router, prefix=settings.api_v1_prefix)
app.include_router(watchlist.router, prefix=settings.api_v1_prefix)
