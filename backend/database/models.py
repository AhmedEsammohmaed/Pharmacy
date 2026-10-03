"""Compatibility imports for model references under backend.database."""

from backend.models import (
    InventoryBatch, Pharmacy, Product, Purchase, PurchaseItem, PurchaseStatus,
    Sale, SaleItem, SaleItemBatch, Supplier, TenantScoped, User, UserSession,
)

__all__ = [
    "InventoryBatch", "Pharmacy", "Product", "Purchase", "PurchaseItem", "PurchaseStatus",
    "Sale", "SaleItem", "SaleItemBatch", "Supplier", "TenantScoped", "User", "UserSession",
]
