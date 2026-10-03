from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import (
    InventoryAnalyticsRead,
    SalesSummaryRead,
    TopProductRead,
)
from backend.services.analytics_service import (
    get_inventory_analytics,
    get_sales_summary,
    get_top_products,
)


router = APIRouter(prefix="/analytics", tags=["Analytics"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/sales/summary", response_model=SalesSummaryRead)
def sales_summary(
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SalesSummaryRead:
    return get_sales_summary(db, start_date, end_date)


@router.get("/sales/top-products", response_model=list[TopProductRead])
def top_products(
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=10, ge=1, le=100),
) -> list[TopProductRead]:
    return get_top_products(db, start_date, end_date, limit)


@router.get("/inventory", response_model=InventoryAnalyticsRead)
def inventory_analytics(
    db: DbSession,
    expiry_window_days: int = Query(default=30, ge=1, le=365),
) -> InventoryAnalyticsRead:
    return get_inventory_analytics(db, expiry_window_days)
