"""Daily, tenant-scoped pharmacy inventory alert automation."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from threading import Lock

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import (
    AutomationAlert,
    AutomationRule,
    InventoryBatch,
    Pharmacy,
    Product,
    utc_now,
)
from backend.time_utils import business_today

logger = logging.getLogger(__name__)
DEFAULT_LOW_STOCK_THRESHOLD = 10
DEFAULT_EXPIRY_NOTICE_DAYS = 30
_RUN_LOCK = Lock()


def get_settings(db: Session, tenant_id: int) -> dict[str, int | bool]:
    db.info["tenant_id"] = tenant_id
    rule = db.scalar(
        select(AutomationRule).where(AutomationRule.tenant_id == tenant_id)
    )
    if rule is None:
        return {
            "enabled": True,
            "low_stock_threshold": DEFAULT_LOW_STOCK_THRESHOLD,
            "expiry_notice_days": DEFAULT_EXPIRY_NOTICE_DAYS,
        }
    return {
        "enabled": rule.enabled,
        "low_stock_threshold": rule.low_stock_threshold,
        "expiry_notice_days": rule.expiry_notice_days,
    }


def save_settings(
    db: Session,
    tenant_id: int,
    *,
    enabled: bool,
    low_stock_threshold: int,
    expiry_notice_days: int,
) -> dict[str, int | bool]:
    db.info["tenant_id"] = tenant_id
    rule = db.scalar(
        select(AutomationRule).where(AutomationRule.tenant_id == tenant_id)
    )
    if rule is None:
        rule = AutomationRule(tenant_id=tenant_id)
        db.add(rule)
    rule.enabled = enabled
    rule.low_stock_threshold = low_stock_threshold
    rule.expiry_notice_days = expiry_notice_days
    if not enabled:
        db.execute(
            update(AutomationAlert)
            .where(
                AutomationAlert.tenant_id == tenant_id,
                AutomationAlert.is_active.is_(True),
            )
            .values(is_active=False)
        )
    db.commit()
    return get_settings(db, tenant_id)


def list_active_alerts(db: Session, tenant_id: int, limit: int = 100) -> list[AutomationAlert]:
    db.info["tenant_id"] = tenant_id
    return list(
        db.scalars(
            select(AutomationAlert)
            .where(
                AutomationAlert.tenant_id == tenant_id,
                AutomationAlert.is_active.is_(True),
            )
            .order_by(AutomationAlert.kind, AutomationAlert.last_seen_at.desc())
            .limit(limit)
        )
    )


def _upsert_alert(
    db: Session,
    tenant_id: int,
    *,
    fingerprint: str,
    kind: str,
    title: str,
    message: str,
) -> bool:
    alert = db.scalar(
        select(AutomationAlert).where(
            AutomationAlert.tenant_id == tenant_id,
            AutomationAlert.fingerprint == fingerprint,
        )
    )
    now = utc_now()
    if alert is None:
        db.add(
            AutomationAlert(
                tenant_id=tenant_id,
                fingerprint=fingerprint,
                kind=kind,
                title=title,
                message=message,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        return True
    was_active = alert.is_active
    alert.kind = kind
    alert.title = title
    alert.message = message
    alert.is_active = True
    alert.last_seen_at = now
    return not was_active


def run_for_pharmacy(db: Session, tenant_id: int) -> dict[str, int | str]:
    """Reconcile inventory alerts for one pharmacy; business stock is never changed."""
    db.info["tenant_id"] = tenant_id
    settings = get_settings(db, tenant_id)
    today = business_today()
    if not settings["enabled"]:
        return {"as_of_date": today.isoformat(), "active_alerts": 0, "new_alerts": 0}

    threshold = int(settings["low_stock_threshold"])
    expiry_days = int(settings["expiry_notice_days"])
    all_products = list(
        db.scalars(
            select(Product)
            .where(Product.tenant_id == tenant_id)
            .order_by(Product.name)
        )
    )
    batches = list(
        db.scalars(
            select(InventoryBatch)
            .where(InventoryBatch.tenant_id == tenant_id, InventoryBatch.quantity > 0)
            .order_by(InventoryBatch.expiry_date, InventoryBatch.id)
        )
    )
    product_names = {product.id: product.name for product in all_products}
    active_products = [product for product in all_products if product.is_active]
    sellable_by_product: dict[int, int] = defaultdict(int)
    for batch in batches:
        if batch.expiry_date >= today:
            sellable_by_product[batch.product_id] += batch.quantity

    fingerprints: set[str] = set()
    new_alerts = 0
    for product in active_products:
        sellable = sellable_by_product[product.id]
        if sellable <= threshold:
            fingerprint = f"low-stock:{product.id}"
            fingerprints.add(fingerprint)
            new_alerts += _upsert_alert(
                db,
                tenant_id,
                fingerprint=fingerprint,
                kind="low_stock",
                title=f"Low stock: {product.name}",
                message=f"{product.name} has {sellable} sellable units; the alert threshold is {threshold}.",
            )

    end_date = today + timedelta(days=expiry_days)
    active_batches = 0
    for batch in batches:
        # Archived products still need expiry alerts for stock on hand.
        product_name = product_names.get(batch.product_id)
        if product_name is None:
            continue

        if batch.expiry_date < today:
            kind = "expired_batch"
            fingerprint = f"expired-batch:{batch.id}"
            title = f"Expired stock: {product_name}"
            message = f"Batch {batch.batch_number} has {batch.quantity} units past expiry ({batch.expiry_date.isoformat()})."
        elif batch.expiry_date <= end_date:
            kind = "expiring_batch"
            fingerprint = f"expiring-batch:{batch.id}"
            title = f"Expiry approaching: {product_name}"
            message = f"Batch {batch.batch_number} has {batch.quantity} units expiring on {batch.expiry_date.isoformat()} ({(batch.expiry_date - today).days} days)."
        else:
            continue

        fingerprints.add(fingerprint)
        active_batches += 1
        new_alerts += _upsert_alert(
            db,
            tenant_id,
            fingerprint=fingerprint,
            kind=kind,
            title=title,
            message=message,
        )

    current_alerts = list(
        db.scalars(
            select(AutomationAlert).where(
                AutomationAlert.tenant_id == tenant_id,
                AutomationAlert.is_active.is_(True),
            )
        )
    )
    for alert in current_alerts:
        if alert.fingerprint not in fingerprints:
            alert.is_active = False
            alert.last_seen_at = utc_now()

    db.commit()
    return {
        "as_of_date": today.isoformat(),
        "active_alerts": len(fingerprints),
        "new_alerts": new_alerts,
    }


def run_daily_automations() -> None:
    """Run the scheduled inventory scan for each pharmacy account."""
    if not _RUN_LOCK.acquire(blocking=False):
        logger.info("Skipping overlapping daily pharmacy automation run.")
        return
    try:
        with SessionLocal() as db:
            tenant_ids = list(db.scalars(select(Pharmacy.id).order_by(Pharmacy.id)))
        for tenant_id in tenant_ids:
            try:
                with SessionLocal() as db:
                    result = run_for_pharmacy(db, tenant_id)
                logger.info(
                    "Daily pharmacy inventory automation completed: active_alerts=%s new_alerts=%s",
                    result["active_alerts"],
                    result["new_alerts"],
                )
            except Exception:
                logger.exception("Daily pharmacy inventory automation failed for one account.")
    finally:
        _RUN_LOCK.release()
