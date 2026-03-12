from typing import Optional
from pydantic import BaseModel, Field

# Re-export moved schemas for backward compatibility
from app.schemas.watchlist import WatchlistCreate, WatchlistItemCreate  # noqa: F401
from app.schemas.recorrentes import RecorrenteCreate, RecorrenteUpdate  # noqa: F401


class PatrimonioSnapshotCreate(BaseModel):
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    total_ativos: Optional[float] = Field(default=0, ge=0)
    total_passivos: Optional[float] = Field(default=0, ge=0)
    patrimonio_liquido: Optional[float] = None
    detalhamento: Optional[dict] = None
