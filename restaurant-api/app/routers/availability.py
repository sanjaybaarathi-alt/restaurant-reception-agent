"""Availability endpoint — finds tables that fit a party at a given slot."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/availability", tags=["availability"])


@router.get("", response_model=schemas.AvailabilityOut)
def check_availability(
    slot_datetime: datetime,
    party_size: int,
    location: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if party_size <= 0:
        raise HTTPException(status_code=422, detail="party_size must be positive")

    if slot_datetime < datetime.now():
        raise HTTPException(status_code=422, detail="Cannot check availability for a past time")

    q = db.query(models.Table).filter(models.Table.capacity >= party_size)
    if location:
        q = q.filter(models.Table.location == location)
    candidate_tables = q.order_by(models.Table.capacity, models.Table.table_number).all()

    booked_table_ids = {
        r.table_id
        for r in db.query(models.Reservation)
        .filter(
            models.Reservation.slot_datetime == slot_datetime,
            models.Reservation.status == "confirmed",
        )
        .all()
    }

    available = [
        schemas.AvailableTable(
            table_id=t.id,
            table_number=t.table_number,
            capacity=t.capacity,
            location=t.location,
        )
        for t in candidate_tables
        if t.id not in booked_table_ids
    ]

    return schemas.AvailabilityOut(
        slot_datetime=slot_datetime,
        party_size=party_size,
        available_tables=available,
    )
