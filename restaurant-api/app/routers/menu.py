"""Menu endpoints with filtering on category, tags, price, availability."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("", response_model=List[schemas.MenuItemOut])
def list_menu(
    category: Optional[str] = None,
    tags_any: Optional[List[str]] = Query(
        default=None,
        description="Match items having ANY of these tags",
    ),
    tags_all: Optional[List[str]] = Query(
        default=None,
        description="Match items having ALL of these tags",
    ),
    exclude_tags: Optional[List[str]] = Query(
        default=None,
        description="Exclude items having ANY of these tags",
    ),
    max_price: Optional[float] = None,
    available_only: bool = True,
    db: Session = Depends(get_db),
):
    items = db.query(models.MenuItem).all()
    out = []
    for it in items:
        if available_only and not it.available:
            continue
        if category and it.category != category:
            continue
        if max_price is not None and it.price > max_price:
            continue
        item_tags = set(it.tags or [])
        if tags_any and not (item_tags & set(tags_any)):
            continue
        if tags_all and not set(tags_all).issubset(item_tags):
            continue
        if exclude_tags and (item_tags & set(exclude_tags)):
            continue
        out.append(it)
    return out


@router.get("/{item_id}", response_model=schemas.MenuItemOut)
def get_menu_item(item_id: int, db: Session = Depends(get_db)):
    it = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.id == item_id)
        .first()
    )
    if not it:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return it
