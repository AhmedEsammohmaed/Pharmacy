from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import InventoryBatch, Product, SaleItemBatch
from backend.schemas import InventoryBatchCreate, InventoryBatchUpdate, StockSummary
from backend.time_utils import business_today


def create_batch(payload: InventoryBatchCreate, db: Session) -> InventoryBatch:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    if not product.is_active:
        raise HTTPException(status_code=409, detail="Cannot receive stock for an archived product.")
    if payload.expiry_date < business_today():
        raise HTTPException(
            status_code=422,
            detail="A new inventory batch cannot already be expired.",
        )

    batch = InventoryBatch(**payload.model_dump())
    db.add(batch)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Inventory batch could not be saved.",
        ) from exc
    db.refresh(batch)
    return batch


def list_batches(
    db: Session,
    product_id: int | None,
    offset: int,
    limit: int,
) -> list[InventoryBatch]:
    statement = select(InventoryBatch).order_by(
        InventoryBatch.expiry_date,
        InventoryBatch.id,
    )
    if product_id is not None:
        statement = statement.where(InventoryBatch.product_id == product_id)
    return list(db.scalars(statement.offset(offset).limit(limit)))


def get_batch(batch_id: int, db: Session) -> InventoryBatch:
    batch = db.get(InventoryBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Inventory batch not found.")
    return batch


def update_batch(
    batch_id: int,
    payload: InventoryBatchUpdate,
    db: Session,
) -> InventoryBatch:
    batch = get_batch(batch_id, db)
    for field, value in payload.model_dump().items():
        setattr(batch, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Inventory batch could not be updated.",
        ) from exc
    db.refresh(batch)
    return batch


def delete_batch(batch_id: int, db: Session) -> None:
    batch = get_batch(batch_id, db)
    has_sales = db.scalar(
        select(SaleItemBatch.id)
        .where(SaleItemBatch.batch_id == batch_id)
        .limit(1)
    )
    if batch.quantity > 0:
        raise HTTPException(
            status_code=409,
            detail="A batch with remaining stock cannot be deleted. Set its verified quantity to zero first.",
        )
    if batch.purchase_item_id is not None or has_sales is not None:
        raise HTTPException(
            status_code=409,
            detail="A batch with purchase or sale history cannot be deleted.",
        )

    db.delete(batch)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Inventory batch is referenced by transaction history.",
        ) from exc


def get_product_stock(product_id: int, db: Session) -> StockSummary:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    batches = list(
        db.scalars(
            select(InventoryBatch).where(InventoryBatch.product_id == product_id)
        )
    )
    today = business_today()
    on_hand = sum(batch.quantity for batch in batches)
    expired = sum(batch.quantity for batch in batches if batch.expiry_date < today)
    return StockSummary(
        product_id=product.id,
        product_name=product.name,
        on_hand_quantity=on_hand,
        sellable_quantity=on_hand - expired,
        expired_quantity=expired,
    )
