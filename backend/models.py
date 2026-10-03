from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.time_utils import business_today


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantScoped:
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pharmacy_id: Mapped[int] = mapped_column(
        ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    pharmacy: Mapped[Pharmacy] = relationship()


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship()


class Product(TenantScoped, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("selling_price >= 0", name="ck_products_selling_price_nonnegative"),
        UniqueConstraint("tenant_id", "barcode", name="uq_products_tenant_barcode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    barcode: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    batches: Mapped[list["InventoryBatch"]] = relationship(back_populates="product")
    sale_items: Mapped[list["SaleItem"]] = relationship(back_populates="product")
    purchase_items: Mapped[list["PurchaseItem"]] = relationship(back_populates="product")


class PurchaseStatus(str, Enum):
    ORDERED = "ordered"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class Supplier(TenantScoped, Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    contact_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="supplier")


class InventoryBatch(TenantScoped, Base):
    __tablename__ = "inventory_batches"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_batches_quantity_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="ck_inventory_batches_unit_cost_nonnegative"),
        Index("ix_inventory_batches_product_expiry", "product_id", "expiry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_items.id", ondelete="RESTRICT"), nullable=True
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, default=business_today, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="batches")
    purchase_item: Mapped["PurchaseItem | None"] = relationship(back_populates="batches")
    sale_allocations: Mapped[list["SaleItemBatch"]] = relationship(back_populates="batch")


class Sale(TenantScoped, Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_sales_total_amount_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), default=Decimal("0.00"), nullable=False
    )

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="SaleItem.id",
    )


class SaleItem(TenantScoped, Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sale_items_unit_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="sale_items")
    batch_allocations: Mapped[list["SaleItemBatch"]] = relationship(
        back_populates="sale_item",
        cascade="all, delete-orphan",
        order_by="SaleItemBatch.id",
    )


class SaleItemBatch(TenantScoped, Base):
    __tablename__ = "sale_item_batches"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_item_batches_quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_sale_item_batches_unit_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_item_id: Mapped[int] = mapped_column(
        ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_batches.id", ondelete="RESTRICT"), nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    sale_item: Mapped[SaleItem] = relationship(back_populates="batch_allocations")
    batch: Mapped[InventoryBatch] = relationship(back_populates="sale_allocations")


class Purchase(TenantScoped, Base):
    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ordered', 'partially_received', 'received', 'cancelled')",
            name="ck_purchases_status",
        ),
        CheckConstraint("total_cost >= 0", name="ck_purchases_total_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=PurchaseStatus.ORDERED.value, nullable=False
    )
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)

    supplier: Mapped[Supplier] = relationship(back_populates="purchases")
    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="purchase",
        cascade="all, delete-orphan",
        order_by="PurchaseItem.id",
    )


class PurchaseItem(TenantScoped, Base):
    __tablename__ = "purchase_items"
    __table_args__ = (
        CheckConstraint("ordered_quantity > 0", name="ck_purchase_items_ordered_positive"),
        CheckConstraint("received_quantity >= 0", name="ck_purchase_items_received_nonnegative"),
        CheckConstraint(
            "received_quantity <= ordered_quantity",
            name="ck_purchase_items_received_lte_ordered",
        ),
        CheckConstraint("unit_cost >= 0", name="ck_purchase_items_unit_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    ordered_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    received_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    purchase: Mapped[Purchase] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="purchase_items")
    batches: Mapped[list[InventoryBatch]] = relationship(back_populates="purchase_item")
