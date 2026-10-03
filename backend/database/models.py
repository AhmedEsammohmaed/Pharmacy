"""Compatibility imports for model references under backend.database."""

from backend.models import (
    AutomationAlert,
    AutomationRule,
    InventoryBatch,
    Pharmacy,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Sale, SaleItem, SaleItemBatch, Supplier, TenantScoped, User, UserSession,
)

__all__ = [
    "AutomationAlert",
    "AutomationRule",
    "InventoryBatch",
    "Pharmacy",
    "Product",
    "Purchase",
    "PurchaseItem",
    "PurchaseStatus",
    "Sale", "SaleItem", "SaleItemBatch", "Supplier", "TenantScoped", "User", "UserSession",
]
