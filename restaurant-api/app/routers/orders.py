"""Order endpoints — items added against an active reservation."""

from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(tags=["orders"])


@router.post(
    "/reservations/{reservation_id}/orders",
    response_model=schemas.OrderOut,
    status_code=201,
)
def add_order(
    reservation_id: int,
    payload: schemas.OrderCreate,
    db: Session = Depends(get_db),
):
    r = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if r.status == "cancelled":
        raise HTTPException(
            status_code=409,
            detail="Cannot order on a cancelled reservation",
        )
    if r.slot_datetime < datetime.now():
        raise HTTPException(
            status_code=409,
            detail="Cannot modify orders for a past reservation",
        )

    item = db.query(models.MenuItem).filter(models.MenuItem.id == payload.menu_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    if not item.available:
        raise HTTPException(
            status_code=409,
            detail=f"'{item.name}' is currently unavailable",
        )

    o = models.Order(
        reservation_id=reservation_id,
        menu_item_id=payload.menu_item_id,
        quantity=payload.quantity,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@router.get(
    "/reservations/{reservation_id}/orders",
    response_model=List[schemas.OrderOut],
)
def list_orders(reservation_id: int, db: Session = Depends(get_db)):
    r = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return r.orders


@router.delete("/orders/{order_id}", status_code=204)
def remove_order(order_id: int, db: Session = Depends(get_db)):
    o = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order item not found")
    o = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order item not found")
    if o.reservation.slot_datetime < datetime.now():
        raise HTTPException(
            status_code=409,
            detail="Cannot modify orders for a past reservation",
        )
    db.delete(o)
    db.commit()
    return None
