"""Read-only, tenant-scoped pharmacy data tools available to the AI agent."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models import InventoryBatch, Product
from backend.services.analytics_service import get_sales_summary
from backend.time_utils import business_today

PHARMACY_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "get_pharmacy_overview",
        "description": "Read a concise overview of this pharmacy's products, sellable stock, expired stock, and stock expiring in the next 30 days.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search_pharmacy_products",
        "description": "Search this pharmacy's product catalog by product name or barcode and return recorded price and stock counts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Product name or barcode to search for."},
                "limit": {"type": "integer", "description": "Maximum matches to return, from 1 to 10."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_low_stock",
        "description": "List active products whose current unexpired sellable stock is at or below the requested threshold.",
        "parameters": {
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "description": "Maximum sellable units to consider low stock; defaults to 10."},
                "limit": {"type": "integer", "description": "Maximum products to return, from 1 to 20."},
            },
        },
    },
    {
        "name": "list_expiring_stock",
        "description": "List positive-quantity batches in this pharmacy that expire within the next requested number of days.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Look-ahead period from 1 to 365 days; defaults to 30."},
                "limit": {"type": "integer", "description": "Maximum batches to return, from 1 to 30."},
            },
        },
    },
    {
        "name": "get_sales_summary",
        "description": "Summarize recorded sales for the last requested number of calendar days, including today; defaults to 7 days.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of calendar days, from 1 to 90."},
            },
        },
    },
]


class PharmacyToolError(ValueError):
    """A safe input error returned when an agent tool receives invalid arguments."""


class PharmacyReadOnlyTools:
    """Execute a fixed allowlist of reads scoped to one pharmacy account."""

    def __init__(self, db: Session, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id
        # Reuse the established analytics service, which expects tenant context.
        self._db.info["tenant_id"] = tenant_id

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tools = {
            "get_pharmacy_overview": self._overview,
            "search_pharmacy_products": self._search_products,
            "list_low_stock": self._low_stock,
            "list_expiring_stock": self._expiring_stock,
            "get_sales_summary": self._sales_summary,
        }
        tool = tools.get(name)
        if tool is None:
            raise PharmacyToolError("That pharmacy data tool is not available.")
        if not isinstance(arguments, dict):
            raise PharmacyToolError("Tool arguments must be an object.")
        return tool(arguments)

    def _bounded_int(
        self,
        arguments: dict[str, Any],
        key: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        value = arguments.get(key, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise PharmacyToolError(f"{key} must be a whole number from {minimum} to {maximum}.")
        return value

    def _stock_by_product(self, product_ids: list[int]) -> dict[int, dict[str, Any]]:
        today = business_today()
        stock = {
            product_id: {
                "on_hand_units": 0,
                "sellable_units": 0,
                "expired_units": 0,
                "nearest_expiry": None,
            }
            for product_id in product_ids
        }
        if not product_ids:
            return stock

        batches = self._db.execute(
            select(
                InventoryBatch.product_id,
                InventoryBatch.quantity,
                InventoryBatch.expiry_date,
            ).where(
                InventoryBatch.tenant_id == self._tenant_id,
                InventoryBatch.product_id.in_(product_ids),
            )
        )
        for product_id, quantity, expiry_date in batches:
            item = stock[product_id]
            item["on_hand_units"] += quantity
            if expiry_date < today:
                item["expired_units"] += quantity
            elif quantity > 0:
                item["sellable_units"] += quantity
                nearest = item["nearest_expiry"]
                if nearest is None or expiry_date < nearest:
                    item["nearest_expiry"] = expiry_date
        for item in stock.values():
            if item["nearest_expiry"] is not None:
                item["nearest_expiry"] = item["nearest_expiry"].isoformat()
        return stock

    def _overview(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        today = business_today()
        products = self._db.scalar(
            select(func.count(Product.id)).where(
                Product.tenant_id == self._tenant_id,
                Product.is_active.is_(True),
            )
        ) or 0
        batches = list(
            self._db.execute(
                select(InventoryBatch.quantity, InventoryBatch.expiry_date).where(
                    InventoryBatch.tenant_id == self._tenant_id,
                )
            )
        )
        sellable_units = sum(quantity for quantity, expiry in batches if expiry >= today)
        expired_units = sum(quantity for quantity, expiry in batches if expiry < today)
        expiring_units = sum(
            quantity
            for quantity, expiry in batches
            if quantity > 0 and today <= expiry <= today + timedelta(days=30)
        )
        return {
            "as_of_date": today.isoformat(),
            "active_products": products,
            "sellable_units": sellable_units,
            "expired_units": expired_units,
            "units_expiring_within_30_days": expiring_units,
        }

    def _search_products(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 120:
            raise PharmacyToolError("query must contain 1 to 120 characters.")
        limit = self._bounded_int(arguments, "limit", default=5, minimum=1, maximum=10)
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        products = list(
            self._db.scalars(
                select(Product)
                .where(
                    Product.tenant_id == self._tenant_id,
                    or_(
                        Product.name.ilike(pattern, escape="\\"),
                        Product.barcode.ilike(pattern, escape="\\"),
                    ),
                )
                .order_by(Product.name)
                .limit(limit)
            )
        )
        stock = self._stock_by_product([product.id for product in products])
        return {
            "query": query.strip(),
            "matches": [
                {
                    "name": product.name,
                    "barcode": product.barcode,
                    "selling_price_egp": str(product.selling_price),
                    "active": product.is_active,
                    **stock[product.id],
                }
                for product in products
            ],
        }

    def _low_stock(self, arguments: dict[str, Any]) -> dict[str, Any]:
        threshold = self._bounded_int(arguments, "threshold", default=10, minimum=0, maximum=10000)
        limit = self._bounded_int(arguments, "limit", default=10, minimum=1, maximum=20)
        products = list(
            self._db.scalars(
                select(Product)
                .where(
                    Product.tenant_id == self._tenant_id,
                    Product.is_active.is_(True),
                )
                .order_by(Product.name)
            )
        )
        stock = self._stock_by_product([product.id for product in products])
        rows = [
            {
                "name": product.name,
                "sellable_units": stock[product.id]["sellable_units"],
                "threshold": threshold,
            }
            for product in products
            if stock[product.id]["sellable_units"] <= threshold
        ]
        rows.sort(key=lambda item: (item["sellable_units"], item["name"].casefold()))
        return {
            "as_of_date": business_today().isoformat(),
            "threshold": threshold,
            "products": rows[:limit],
            "truncated": len(rows) > limit,
        }

    def _expiring_stock(self, arguments: dict[str, Any]) -> dict[str, Any]:
        days = self._bounded_int(arguments, "days", default=30, minimum=1, maximum=365)
        limit = self._bounded_int(arguments, "limit", default=20, minimum=1, maximum=30)
        today = business_today()
        end_date = today + timedelta(days=days)
        rows = self._db.execute(
            select(
                Product.name,
                Product.is_active,
                InventoryBatch.batch_number,
                InventoryBatch.quantity,
                InventoryBatch.expiry_date,
            )
            .join(Product, Product.id == InventoryBatch.product_id)
            .where(
                Product.tenant_id == self._tenant_id,
                InventoryBatch.tenant_id == self._tenant_id,
                InventoryBatch.quantity > 0,
                InventoryBatch.expiry_date >= today,
                InventoryBatch.expiry_date <= end_date,
            )
            .order_by(InventoryBatch.expiry_date, Product.name)
            .limit(limit + 1)
        )
        batches = [
            {
                "product": name,
                "product_active": is_active,
                "batch_number": batch_number,
                "quantity": quantity,
                "expiry_date": expiry_date.isoformat(),
                "days_to_expiry": (expiry_date - today).days,
            }
            for name, is_active, batch_number, quantity, expiry_date in rows
        ]
        return {
            "as_of_date": today.isoformat(),
            "days_ahead": days,
            "batches": batches[:limit],
            "truncated": len(batches) > limit,
        }

    def _sales_summary(self, arguments: dict[str, Any]) -> dict[str, Any]:
        days = self._bounded_int(arguments, "days", default=7, minimum=1, maximum=90)
        today: date = business_today()
        start_date = today - timedelta(days=days - 1)
        summary = get_sales_summary(self._db, start_date=start_date, end_date=today)
        return {
            "start_date": summary.start_date.isoformat(),
            "end_date": summary.end_date.isoformat(),
            "sale_count": summary.sale_count,
            "units_sold": summary.units_sold,
            "revenue_egp": str(summary.revenue),
            "cost_of_goods_sold_egp": str(summary.cost_of_goods_sold),
            "gross_profit_egp": str(summary.gross_profit),
            "gross_margin_percent": str(summary.gross_margin_percent),
        }
