from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import Sale, SaleItem
from backend.schemas import SaleCreate, SaleRead
from backend.services.sales_service import create_sale


router = APIRouter(prefix="/sales", tags=["Sales"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
def create_new_sale(payload: SaleCreate, db: DbSession) -> Sale:
    return create_sale(payload.items, db)


@router.get("/", response_model=list[SaleRead])
def list_sales(
    db: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Sale]:
    statement = (
        select(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.batch_allocations))
        .order_by(Sale.sale_date.desc(), Sale.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).unique())


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: int, db: DbSession) -> Sale:
    statement = (
        select(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.batch_allocations))
        .where(Sale.id == sale_id)
    )
    sale = db.scalar(statement)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found.")
    return sale
