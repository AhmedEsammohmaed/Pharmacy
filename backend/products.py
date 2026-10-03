from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Product
from backend.schemas import ProductCreate, ProductRead, ProductUpdate


router = APIRouter(prefix="/products", tags=["Products"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: DbSession) -> Product:
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A product with this barcode already exists.",
        ) from exc
    db.refresh(product)
    return product


@router.get("/", response_model=list[ProductRead])
def list_products(
    db: DbSession,
    active_only: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Product]:
    statement = select(Product).order_by(Product.name, Product.id).offset(offset).limit(limit)
    if active_only:
        statement = statement.where(Product.is_active.is_(True))
    return list(db.scalars(statement))


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@router.put("/{product_id}", response_model=ProductRead)
def replace_product(product_id: int, payload: ProductCreate, db: DbSession) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    product.name = payload.name
    product.barcode = payload.barcode
    product.description = payload.description
    product.selling_price = payload.selling_price
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A product with this barcode already exists.",
        ) from exc
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, db: DbSession) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A product with this barcode already exists.",
        ) from exc
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_product(product_id: int, db: DbSession) -> Response:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    product.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
