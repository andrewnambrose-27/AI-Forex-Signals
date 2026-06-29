from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.signal import Signal
from app.schemas.signal import SignalRead, SignalRequest
from app.services.signal_engine import generate_signal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/score", response_model=SignalRead)
def score_signal(payload: SignalRequest) -> SignalRead:
    return generate_signal(payload)


@router.get("/history", response_model=list[SignalRead])
def signal_history(db: DbSession, limit: int = 100) -> list[Signal]:
    query = select(Signal).order_by(Signal.created_at.desc()).limit(min(limit, 500))
    return list(db.scalars(query))
