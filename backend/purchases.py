from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import Purchase, PurchaseStatus
from backend.schemas import (
    PurchaseCreate,
    PurchaseRead,
    PurchaseReceiptCreate,
)
from backend.services.purchase_service import create_purchase, receive_purchase_items


router = APIRouter(prefix="/purchases", tags=["Purchasing"])
DbSession = Annotated[Session, Depends(get_db)]


def _purchase_query():
    return select(Purchase).options(selectinload(Purchase.items))


@router.post("/", response_model=PurchaseRead, status_code=status.HTTP_201_CREATED)
def create_new_purchase(payload: PurchaseCreate, db: DbSession) -> Purchase:
    return create_purchase(payload, db)


@router.get("/", response_model=list[PurchaseRead])
def list_purchases(
    db: DbSession,
    purchase_status: PurchaseStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Purchase]:
    statement = (
        _purchase_query()
        .order_by(Purchase.order_date.desc(), Purchase.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if purchase_status is not None:
        statement = statement.where(Purchase.status == purchase_status.value)
    return list(db.scalars(statement).unique())


@router.get("/{purchase_id}", response_model=PurchaseRead)
def get_purchase(purchase_id: int, db: DbSession) -> Purchase:
    purchase = db.scalar(_purchase_query().where(Purchase.id == purchase_id))
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found.")
    return purchase


@router.post("/{purchase_id}/receipts", response_model=PurchaseRead)
def receive_purchase(
    purchase_id: int,
    payload: PurchaseReceiptCreate,
    db: DbSession,
) -> Purchase:
    return receive_purchase_items(purchase_id, payload, db)


@router.post("/{purchase_id}/cancel", response_model=PurchaseRead)
def cancel_purchase(purchase_id: int, db: DbSession) -> Purchase:
    purchase = db.scalar(_purchase_query().where(Purchase.id == purchase_id).with_for_update())
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found.")
    if purchase.status != PurchaseStatus.ORDERED.value:
        raise HTTPException(
            status_code=409,
            detail="Only purchases that have not been received can be cancelled.",
        )
    purchase.status = PurchaseStatus.CANCELLED.value
    db.commit()
    return purchase
