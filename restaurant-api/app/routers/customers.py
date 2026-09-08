"""Customers endpoints — including preference updates and history."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=schemas.CustomerOut, status_code=201)
def create_customer(
    payload: schemas.CustomerCreate, db: Session = Depends(get_db)
):
    existing = None
    if payload.phone:
        existing = (
            db.query(models.Customer)
            .filter(models.Customer.phone == payload.phone)
            .first()
        )
    if not existing and payload.email:
        existing = (
            db.query(models.Customer)
            .filter(models.Customer.email == payload.email)
            .first()
        )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Customer already exists with id {existing.id}",
        )

    c = models.Customer(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        preferences=payload.preferences,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/lookup", response_model=schemas.CustomerOut)
def lookup_customer(
    phone: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Find a customer by phone or email. Returns 404 if no match."""
    if not phone and not email:
        raise HTTPException(
            status_code=400, detail="Provide phone or email"
        )
    q = db.query(models.Customer)
    if phone:
        q = q.filter(models.Customer.phone == phone)
    if email:
        q = q.filter(models.Customer.email == email)
    c = q.first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return c


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    c = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return c


@router.patch(
    "/{customer_id}/preferences", response_model=schemas.CustomerOut
)
def update_preferences(
    customer_id: int,
    payload: schemas.PreferencesUpdate,
    db: Session = Depends(get_db),
):
    """Shallow-merge the given keys into the customer's preferences JSON."""
    c = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    merged = dict(c.preferences or {})
    merged.update(payload.preferences)
    c.preferences = merged
    flag_modified(c, "preferences")
    db.commit()
    db.refresh(c)
    return c


@router.get(
    "/{customer_id}/reservations",
    response_model=List[schemas.ReservationOut],
)
def get_customer_reservations(
    customer_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    c = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    q = db.query(models.Reservation).filter(
        models.Reservation.customer_id == customer_id
    )
    if status:
        q = q.filter(models.Reservation.status == status)
    return q.order_by(models.Reservation.slot_datetime.desc()).all()


@router.get(
    "/{customer_id}/orders", response_model=List[schemas.OrderOut]
)
def get_customer_orders(
    customer_id: int, db: Session = Depends(get_db)
):
    c = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    res_ids = [r.id for r in c.reservations]
    if not res_ids:
        return []
    return (
        db.query(models.Order)
        .filter(models.Order.reservation_id.in_(res_ids))
        .order_by(models.Order.created_at.desc())
        .all()
    )
