"""Pydantic schemas for request bodies and responses."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ----- Tables -----
class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_number: int
    capacity: int
    location: Literal["indoor", "outdoor"]


# ----- Customers -----
class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def at_least_one_contact(self):
        if not self.phone and not self.email:
            raise ValueError("At least one of phone or email is required")
        return self


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    preferences: Dict[str, Any]
    created_at: datetime


class PreferencesUpdate(BaseModel):
    """Partial-merge update for the customer's preferences JSON blob."""

    preferences: Dict[str, Any]


# ----- Menu -----
class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    price: float
    tags: List[str]
    category: Literal["starter", "main", "dessert"]
    available: bool


# ----- Reservations -----
class ReservationCreate(BaseModel):
    customer_id: int
    table_id: int
    slot_datetime: datetime
    party_size: int = Field(gt=0)
    special_requests: Optional[str] = None


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    table_id: int
    slot_datetime: datetime
    party_size: int
    special_requests: Optional[str]
    status: Literal["confirmed", "cancelled", "completed"]
    created_at: datetime


# ----- Orders -----
class OrderCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0, default=1)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int
    menu_item_id: int
    quantity: int
    created_at: datetime


# ----- Availability -----
class AvailableTable(BaseModel):
    table_id: int
    table_number: int
    capacity: int
    location: str


class AvailabilityOut(BaseModel):
    slot_datetime: datetime
    party_size: int
    available_tables: List[AvailableTable]
