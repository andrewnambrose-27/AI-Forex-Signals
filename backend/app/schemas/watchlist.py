from pydantic import BaseModel, Field


class WatchlistPairCreate(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=32, examples=["EURUSD"])
    epic: str | None = Field(None, min_length=3, max_length=128, examples=["CS.D.EURUSD.MINI.IP"])
    name: str | None = None


class WatchlistPairRead(BaseModel):
    id: int
    symbol: str
    epic: str
    name: str | None = None

    model_config = {"from_attributes": True}
