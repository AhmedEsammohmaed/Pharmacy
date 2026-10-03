from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import InventoryBatch
from backend.schemas import (
    InventoryBatchCreate,
    InventoryBatchRead,
    InventoryBatchUpdate,
    StockSummary,
)
from backend.services.inventory_service import (
    create_batch,
    delete_batch,
    get_batch,
    get_product_stock,
    list_batches,
    update_batch,
)


router = APIRouter(prefix="/inventory", tags=["Inventory"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/batches/",
    response_model=InventoryBatchRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post("/", response_model=InventoryBatchRead, status_code=status.HTTP_201_CREATED)
def receive_batch(payload: InventoryBatchCreate, db: DbSession) -> InventoryBatch:
    return create_batch(payload, db)


@router.get(
    "/batches/",
    response_model=list[InventoryBatchRead],
    include_in_schema=False,
)
@router.get("/", response_model=list[InventoryBatchRead])
def list_inventory_batches(
    db: DbSession,
    product_id: int | None = Query(default=None, gt=0),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InventoryBatch]:
    return list_batches(db, product_id, offset, limit)


@router.get("/product/{product_id}/stock", response_model=StockSummary)
def product_stock(product_id: int, db: DbSession) -> StockSummary:
    return get_product_stock(product_id, db)


@router.get("/stock/{product_id}", response_model=StockSummary, include_in_schema=False)
def legacy_product_stock(product_id: int, db: DbSession) -> StockSummary:
    return get_product_stock(product_id, db)


@router.get("/{batch_id}", response_model=InventoryBatchRead)
def inventory_batch(batch_id: int, db: DbSession) -> InventoryBatch:
    return get_batch(batch_id, db)


@router.put("/{batch_id}", response_model=InventoryBatchRead)
def replace_inventory_batch(
    batch_id: int,
    payload: InventoryBatchUpdate,
    db: DbSession,
) -> InventoryBatch:
    return update_batch(batch_id, payload, db)


@router.delete(
    "/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_inventory_batch(batch_id: int, db: DbSession) -> Response:
    delete_batch(batch_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
