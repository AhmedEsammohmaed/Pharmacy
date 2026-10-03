from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models import PurchaseStatus


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    barcode: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    selling_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("name", "barcode", mode="before")
    @classmethod
    def trim_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    barcode: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    selling_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_active: bool | None = None

    @field_validator("name", "barcode", "description", mode="before")
    @classmethod
    def trim_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def reject_empty_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in ("name", "selling_price", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class ProductRead(BaseModel):
    id: int
    name: str
    barcode: str | None
    description: str | None
    selling_price: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryBatchCreate(BaseModel):
    product_id: int = Field(gt=0)
    batch_number: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    expiry_date: date

    @field_validator("batch_number")
    @classmethod
    def trim_batch_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Batch number cannot be blank.")
        return value


class InventoryBatchRead(BaseModel):
    id: int
    product_id: int
    purchase_item_id: int | None
    batch_number: str
    quantity: int
    unit_cost: Decimal
    received_on: date
    expiry_date: date
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryBatchUpdate(BaseModel):
    batch_number: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=0, le=1_000_000)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    expiry_date: date

    @field_validator("batch_number")
    @classmethod
    def trim_batch_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Batch number cannot be blank.")
        return value


class StockSummary(BaseModel):
    product_id: int
    product_name: str
    on_hand_quantity: int
    sellable_quantity: int
    expired_quantity: int


class SaleItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100_000)


class SaleCreate(BaseModel):
    items: list[SaleItemCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_products(self):
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("A product can appear only once in a sale.")
        return self


class SaleItemBatchRead(BaseModel):
    id: int
    batch_id: int
    batch_number: str
    quantity: int
    unit_cost: Decimal

    model_config = ConfigDict(from_attributes=True)


class SaleItemRead(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    batch_allocations: list[SaleItemBatchRead]

    model_config = ConfigDict(from_attributes=True)


class SaleRead(BaseModel):
    id: int
    sale_date: datetime
    total_amount: Decimal
    items: list[SaleItemRead]

    model_config = ConfigDict(from_attributes=True)


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("name", "contact_person", "phone", "email", mode="before")
    @classmethod
    def trim_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    is_active: bool | None = None

    @field_validator("name", "contact_person", "phone", "email", mode="before")
    @classmethod
    def trim_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null or blank.")
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active cannot be null.")
        return self


class SupplierRead(BaseModel):
    id: int
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    ordered_quantity: int = Field(gt=0, le=100_000)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PurchaseCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    items: list[PurchaseItemCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_products(self):
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("A product can appear only once in a purchase.")
        return self


class PurchaseReceiptItemCreate(BaseModel):
    purchase_item_id: int = Field(gt=0)
    batch_number: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=100_000)
    expiry_date: date

    @field_validator("batch_number")
    @classmethod
    def trim_batch_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Batch number cannot be blank.")
        return value


class PurchaseReceiptCreate(BaseModel):
    items: list[PurchaseReceiptItemCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_lines(self):
        purchase_item_ids = [item.purchase_item_id for item in self.items]
        if len(purchase_item_ids) != len(set(purchase_item_ids)):
            raise ValueError("A purchase line can appear only once in a receipt.")
        return self


class PurchaseItemRead(BaseModel):
    id: int
    product_id: int
    ordered_quantity: int
    received_quantity: int
    unit_cost: Decimal

    model_config = ConfigDict(from_attributes=True)


class PurchaseRead(BaseModel):
    id: int
    supplier_id: int
    order_date: datetime
    status: PurchaseStatus
    total_cost: Decimal
    items: list[PurchaseItemRead]

    model_config = ConfigDict(from_attributes=True)


class SalesSummaryRead(BaseModel):
    start_date: date
    end_date: date
    sale_count: int
    units_sold: int
    revenue: Decimal
    cost_of_goods_sold: Decimal
    gross_profit: Decimal
    gross_margin_percent: Decimal


class TopProductRead(BaseModel):
    product_id: int
    product_name: str
    units_sold: int
    revenue: Decimal


class ExpiringBatchRead(BaseModel):
    batch_id: int
    product_id: int
    product_name: str
    batch_number: str
    quantity: int
    unit_cost: Decimal
    expiry_date: date
    days_to_expiry: int


class InventoryAnalyticsRead(BaseModel):
    as_of_date: date
    on_hand_units: int
    sellable_units: int
    expired_units: int
    inventory_cost_value: Decimal
    expired_cost_value: Decimal
    near_expiry_batch_count: int
    near_expiry_units: int
    near_expiry_batches: list[ExpiringBatchRead]
