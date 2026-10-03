"""Compatibility imports for singular model module references."""

from backend.models import (
    InventoryBatch, Pharmacy, Product, Purchase, PurchaseItem, Sale, SaleItem, Supplier,
    User, UserSession,
)

__all__ = [
    "InventoryBatch", "Pharmacy", "Product", "Purchase", "PurchaseItem", "Sale", "SaleItem",
    "Supplier", "User", "UserSession",
]
