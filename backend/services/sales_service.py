from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import InventoryBatch, Product, Sale, SaleItem, SaleItemBatch
from backend.schemas import SaleItemCreate
from backend.time_utils import business_today


def create_sale(items: list[SaleItemCreate], db: Session) -> Sale:
    if not items:
        raise HTTPException(status_code=400, detail="A sale must contain at least one item.")

    products: dict[int, Product] = {}
    batches_by_product: dict[int, list[InventoryBatch]] = {}
    today = business_today()

    # Validate the entire request before changing stock.
    for item in items:
        if item.product_id in products:
            raise HTTPException(
                status_code=400,
                detail=f"Product {item.product_id} appears more than once in the sale.",
            )

        product = db.get(Product, item.product_id)
        if product is None or not product.is_active:
            raise HTTPException(
                status_code=404,
                detail=f"Active product {item.product_id} was not found.",
            )

        batches = list(
            db.scalars(
                select(InventoryBatch)
                .where(
                    InventoryBatch.product_id == product.id,
                    InventoryBatch.quantity > 0,
                    InventoryBatch.expiry_date >= today,
                )
                .order_by(InventoryBatch.expiry_date, InventoryBatch.id)
                .with_for_update()
            )
        )
        available = sum(batch.quantity for batch in batches)
        if available < item.quantity:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Insufficient sellable stock for {product.name}. "
                    f"Available: {available}; requested: {item.quantity}."
                ),
            )

        products[product.id] = product
        batches_by_product[product.id] = batches

    sale = Sale(total_amount=Decimal("0.00"))
    total_amount = Decimal("0.00")

    try:
        for item in items:
            product = products[item.product_id]
            unit_price = product.selling_price
            sale_item = SaleItem(
                product=product,
                quantity=item.quantity,
                unit_price=unit_price,
            )
            sale.items.append(sale_item)
            total_amount += unit_price * item.quantity

            remaining = item.quantity
            for batch in batches_by_product[product.id]:
                if remaining == 0:
                    break

                quantity_taken = min(batch.quantity, remaining)
                result = db.execute(
                    update(InventoryBatch)
                    .where(
                        InventoryBatch.id == batch.id,
                        InventoryBatch.quantity == batch.quantity,
                    )
                    .values(quantity=InventoryBatch.quantity - quantity_taken)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    raise HTTPException(
                        status_code=409,
                        detail="Inventory changed during checkout. Retry the sale.",
                    )

                sale_item.batch_allocations.append(
                    SaleItemBatch(
                        batch_id=batch.id,
                        batch_number=batch.batch_number,
                        quantity=quantity_taken,
                        unit_cost=batch.unit_cost,
                    )
                )
                remaining -= quantity_taken

        sale.total_amount = total_amount
        db.add(sale)
        db.commit()
        db.refresh(sale)
        return sale
    except Exception:
        db.rollback()
        raise
