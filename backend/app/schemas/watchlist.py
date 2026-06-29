from pydantic import BaseModel, Field


class WatchlistPairCreate(BaseModel):
    symbol: str = Field(..., min_length=6, max_length=12, examples=["EURUSD"])


class WatchlistPairRead(BaseModel):
    id: int
    symbol: str

    model_config = {"from_attributes": True}
