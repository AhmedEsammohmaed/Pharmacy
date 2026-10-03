from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Supplier
from backend.schemas import SupplierCreate, SupplierRead, SupplierUpdate


router = APIRouter(prefix="/suppliers", tags=["Suppliers"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: DbSession) -> Supplier:
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/", response_model=list[SupplierRead])
def list_suppliers(
    db: DbSession,
    active_only: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Supplier]:
    statement = select(Supplier).order_by(Supplier.name, Supplier.id).offset(offset).limit(limit)
    if active_only:
        statement = statement.where(Supplier.is_active.is_(True))
    return list(db.scalars(statement))


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: int, db: DbSession) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: DbSession) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_supplier(supplier_id: int, db: DbSession) -> Response:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    supplier.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
