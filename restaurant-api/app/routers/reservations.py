"""Reservations endpoints with capacity checks, double-booking prevention,
and cancellation cutoff."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/reservations", tags=["reservations"])

CANCELLATION_CUTOFF_HOURS = 2


def _is_valid_slot(dt: datetime) -> bool:
    """Slots are 30-min increments from 12:00 to 22:30 inclusive."""
    if dt.minute not in (0, 30) or dt.second != 0 or dt.microsecond != 0:
        return False
    if dt.hour < 12 or dt.hour > 22:
        return False
    if dt.hour == 22 and dt.minute > 30:
        return False
    return True


@router.post("", response_model=schemas.ReservationOut, status_code=201)
def create_reservation(payload: schemas.ReservationCreate, db: Session = Depends(get_db)):
    if not _is_valid_slot(payload.slot_datetime):
        raise HTTPException(
            status_code=422,
            detail=("slot_datetime must be on a 30-min boundary between 12:00 and 22:30"),
        )

    if payload.slot_datetime < datetime.now():
        raise HTTPException(
            status_code=422,
            detail="Cannot create a reservation in the past",
        )

    customer = db.query(models.Customer).filter(models.Customer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    table = db.query(models.Table).filter(models.Table.id == payload.table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    if payload.party_size > table.capacity:
        raise HTTPException(
            status_code=422,
            detail=(f"Party of {payload.party_size} exceeds table capacity {table.capacity}"),
        )

    conflict = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.table_id == payload.table_id,
            models.Reservation.slot_datetime == payload.slot_datetime,
            models.Reservation.status == "confirmed",
        )
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=(f"Table {table.table_number} is already booked at this slot"),
        )

    r = models.Reservation(
        customer_id=payload.customer_id,
        table_id=payload.table_id,
        slot_datetime=payload.slot_datetime,
        party_size=payload.party_size,
        special_requests=payload.special_requests,
        status="confirmed",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("/{reservation_id}", response_model=schemas.ReservationOut)
def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    r = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if r.status == "confirmed" and r.slot_datetime < datetime.now():
        r.status = "completed"
        db.commit()
        db.refresh(r)
    return r


@router.delete("/{reservation_id}", response_model=schemas.ReservationOut)
def cancel_reservation(reservation_id: int, db: Session = Depends(get_db)):
    r = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if r.status == "cancelled":
        raise HTTPException(status_code=409, detail="Reservation already cancelled")

    cutoff = r.slot_datetime - timedelta(hours=CANCELLATION_CUTOFF_HOURS)
    if datetime.now() > cutoff:
        raise HTTPException(
            status_code=409,
            detail=(f"Cannot cancel within {CANCELLATION_CUTOFF_HOURS} hours of the reservation"),
        )

    r.status = "cancelled"
    db.commit()
    db.refresh(r)
    return r
