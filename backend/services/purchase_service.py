from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    InventoryBatch,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Supplier,
)
from backend.schemas import PurchaseCreate, PurchaseReceiptCreate


def create_purchase(payload: PurchaseCreate, db: Session) -> Purchase:
    supplier = db.get(Supplier, payload.supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    if not supplier.is_active:
        raise HTTPException(status_code=409, detail="Cannot order from an archived supplier.")

    total_cost = Decimal("0.00")
    purchase = Purchase(
        supplier=supplier,
        status=PurchaseStatus.ORDERED.value,
        total_cost=Decimal("0.00"),
    )
    for item in payload.items:
        product = db.get(Product, item.product_id)
        if product is None or not product.is_active:
            raise HTTPException(
                status_code=404,
                detail=f"Active product {item.product_id} was not found.",
            )
        purchase.items.append(
            PurchaseItem(
                product=product,
                ordered_quantity=item.ordered_quantity,
                received_quantity=0,
                unit_cost=item.unit_cost,
            )
        )
        total_cost += item.unit_cost * item.ordered_quantity

    purchase.total_cost = total_cost
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    return purchase


def receive_purchase_items(
    purchase_id: int,
    payload: PurchaseReceiptCreate,
    db: Session,
) -> Purchase:
    statement = (
        select(Purchase)
        .options(selectinload(Purchase.items))
        .where(Purchase.id == purchase_id)
        .with_for_update()
    )
    purchase = db.scalar(statement)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found.")
    if purchase.status in (PurchaseStatus.RECEIVED.value, PurchaseStatus.CANCELLED.value):
        raise HTTPException(status_code=409, detail="This purchase can no longer be received.")

    purchase_items = {item.id: item for item in purchase.items}
    try:
        for received in payload.items:
            purchase_item = purchase_items.get(received.purchase_item_id)
            if purchase_item is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Purchase line {received.purchase_item_id} was not found.",
                )

            result = db.execute(
                update(PurchaseItem)
                .where(
                    PurchaseItem.id == purchase_item.id,
                    PurchaseItem.purchase_id == purchase.id,
                    PurchaseItem.received_quantity + received.quantity
                    <= PurchaseItem.ordered_quantity,
                )
                .values(
                    received_quantity=PurchaseItem.received_quantity + received.quantity
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Receipt exceeds the remaining quantity for "
                        f"purchase line {purchase_item.id}."
                    ),
                )

            purchase_item.received_quantity += received.quantity
            db.add(
                InventoryBatch(
                    product_id=purchase_item.product_id,
                    purchase_item_id=purchase_item.id,
                    batch_number=received.batch_number,
                    quantity=received.quantity,
                    unit_cost=purchase_item.unit_cost,
                    expiry_date=received.expiry_date,
                )
            )

        if all(item.received_quantity == item.ordered_quantity for item in purchase.items):
            purchase.status = PurchaseStatus.RECEIVED.value
        else:
            purchase.status = PurchaseStatus.PARTIALLY_RECEIVED.value

        db.commit()
        db.refresh(purchase)
        return purchase
    except Exception:
        db.rollback()
        raise
