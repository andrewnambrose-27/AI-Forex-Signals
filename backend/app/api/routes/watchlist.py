from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.watchlist import WatchlistPair
from app.schemas.watchlist import WatchlistPairCreate, WatchlistPairRead

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistPairRead])
def list_watchlist(db: DbSession) -> list[WatchlistPair]:
    return list(db.scalars(select(WatchlistPair).order_by(WatchlistPair.symbol.asc())))


@router.post("", response_model=WatchlistPairRead)
def add_watchlist_pair(payload: WatchlistPairCreate, db: DbSession) -> WatchlistPair:
    pair = WatchlistPair(user_id=None, symbol=payload.symbol.upper())
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return pair
