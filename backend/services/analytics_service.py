from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import InventoryBatch, Product, Sale, SaleItem, SaleItemBatch
from backend.schemas import (
    ExpiringBatchRead,
    InventoryAnalyticsRead,
    SalesSummaryRead,
    TopProductRead,
)
from backend.time_utils import business_timezone, business_today


def _utc_range(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date, datetime, datetime]:
    start = start_date or end_date or business_today()
    end = end_date or start
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date.")
    local_timezone = business_timezone()
    start_at = datetime.combine(start, time.min, tzinfo=local_timezone).astimezone(timezone.utc)
    end_exclusive = datetime.combine(
        end + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    ).astimezone(timezone.utc)
    return start, end, start_at, end_exclusive


def get_sales_summary(
    db: Session,
    start_date: date | None,
    end_date: date | None,
) -> SalesSummaryRead:
    tenant_id = db.info["tenant_id"]
    report_start, report_end, start_at, end_exclusive = _utc_range(start_date, end_date)
    sale_count = db.scalar(
        select(func.count(Sale.id)).where(
            Sale.sale_date >= start_at,
            Sale.sale_date < end_exclusive,
            Sale.tenant_id == tenant_id,
        )
    ) or 0
    sale_lines = db.execute(
        select(SaleItem.quantity, SaleItem.unit_price)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.sale_date >= start_at,
            Sale.sale_date < end_exclusive,
            Sale.tenant_id == tenant_id,
            SaleItem.tenant_id == tenant_id,
        )
    )
    units_sold = 0
    revenue = Decimal("0.00")
    for quantity, unit_price in sale_lines:
        units_sold += quantity
        revenue += unit_price * quantity

    cost_lines = db.execute(
        select(SaleItemBatch.quantity, SaleItemBatch.unit_cost)
        .join(SaleItem, SaleItem.id == SaleItemBatch.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.sale_date >= start_at,
            Sale.sale_date < end_exclusive,
            Sale.tenant_id == tenant_id,
            SaleItem.tenant_id == tenant_id,
            SaleItemBatch.tenant_id == tenant_id,
        )
    )
    cost_of_goods_sold = sum(
        (quantity * unit_cost for quantity, unit_cost in cost_lines),
        Decimal("0.00"),
    )
    gross_profit = revenue - cost_of_goods_sold
    gross_margin = (
        (gross_profit * Decimal("100") / revenue).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if revenue
        else Decimal("0.00")
    )
    return SalesSummaryRead(
        start_date=report_start,
        end_date=report_end,
        sale_count=sale_count,
        units_sold=units_sold,
        revenue=revenue,
        cost_of_goods_sold=cost_of_goods_sold,
        gross_profit=gross_profit,
        gross_margin_percent=gross_margin,
    )


def get_top_products(
    db: Session,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> list[TopProductRead]:
    tenant_id = db.info["tenant_id"]
    _, _, start_at, end_exclusive = _utc_range(start_date, end_date)
    rows = db.execute(
        select(
            Product.id,
            Product.name,
            SaleItem.quantity,
            SaleItem.unit_price,
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.sale_date >= start_at,
            Sale.sale_date < end_exclusive,
            Product.tenant_id == tenant_id,
            SaleItem.tenant_id == tenant_id,
            Sale.tenant_id == tenant_id,
        )
    )
    totals: dict[int, tuple[str, int, Decimal]] = {}
    for product_id, name, quantity, unit_price in rows:
        prior_name, prior_quantity, prior_revenue = totals.get(
            product_id,
            (name, 0, Decimal("0.00")),
        )
        totals[product_id] = (
            prior_name,
            prior_quantity + quantity,
            prior_revenue + unit_price * quantity,
        )

    ranked = sorted(totals.items(), key=lambda row: (-row[1][1], row[1][0]))[:limit]
    return [
        TopProductRead(
            product_id=product_id,
            product_name=name,
            units_sold=quantity,
            revenue=revenue,
        )
        for product_id, (name, quantity, revenue) in ranked
    ]


def get_inventory_analytics(db: Session, expiry_window_days: int) -> InventoryAnalyticsRead:
    tenant_id = db.info["tenant_id"]
    today = business_today()
    batches = list(
        db.scalars(
            select(InventoryBatch)
            .where(InventoryBatch.tenant_id == tenant_id)
            .order_by(InventoryBatch.expiry_date, InventoryBatch.id)
        )
    )
    product_ids = {batch.product_id for batch in batches}
    products = (
        {
            product.id: product.name
            for product in db.scalars(
                select(Product).where(
                    Product.id.in_(product_ids),
                    Product.tenant_id == tenant_id,
                )
            )
        }
        if product_ids
        else {}
    )

    on_hand_units = sum(batch.quantity for batch in batches)
    expired_batches = [batch for batch in batches if batch.expiry_date < today]
    expired_units = sum(batch.quantity for batch in expired_batches)
    near_expiry = [
        batch
        for batch in batches
        if today <= batch.expiry_date <= today + timedelta(days=expiry_window_days)
        and batch.quantity > 0
    ]
    expiring_batches = [
        ExpiringBatchRead(
            batch_id=batch.id,
            product_id=batch.product_id,
            product_name=products[batch.product_id],
            batch_number=batch.batch_number,
            quantity=batch.quantity,
            unit_cost=batch.unit_cost,
            expiry_date=batch.expiry_date,
            days_to_expiry=(batch.expiry_date - today).days,
        )
        for batch in near_expiry
    ]
    expired_value = sum(
        (batch.unit_cost * batch.quantity for batch in expired_batches),
        Decimal("0.00"),
    )
    total_value = sum(
        (batch.unit_cost * batch.quantity for batch in batches),
        Decimal("0.00"),
    )
    return InventoryAnalyticsRead(
        as_of_date=today,
        on_hand_units=on_hand_units,
        sellable_units=on_hand_units - expired_units,
        expired_units=expired_units,
        inventory_cost_value=total_value,
        expired_cost_value=expired_value,
        near_expiry_batch_count=len(expiring_batches),
        near_expiry_units=sum(batch.quantity for batch in near_expiry),
        near_expiry_batches=expiring_batches,
    )
