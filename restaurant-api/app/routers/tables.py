"""Tables endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=List[schemas.TableOut])
def list_tables(
    location: Optional[str] = None,
    min_capacity: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Table)
    if location:
        q = q.filter(models.Table.location == location)
    if min_capacity is not None:
        q = q.filter(models.Table.capacity >= min_capacity)
    return q.order_by(models.Table.capacity, models.Table.table_number).all()


@router.get("/{table_id}", response_model=schemas.TableOut)
def get_table(table_id: int, db: Session = Depends(get_db)):
    t = db.query(models.Table).filter(models.Table.id == table_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Table not found")
    return t
