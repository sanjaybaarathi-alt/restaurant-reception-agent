"""Typed models for the supplied Restaurant Reservation API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Customer(DomainModel):
    id: int
    name: str
    phone: str | None
    email: str | None
    preferences: dict[str, Any]
    created_at: datetime


class MenuItem(DomainModel):
    id: int
    name: str
    description: str
    price: float
    tags: list[str]
    category: Literal["starter", "main", "dessert"]
    available: bool


class AvailableTable(DomainModel):
    table_id: int
    table_number: int
    capacity: int
    location: Literal["indoor", "outdoor"]


class Availability(DomainModel):
    slot_datetime: datetime
    party_size: int
    available_tables: list[AvailableTable]


class Reservation(DomainModel):
    id: int
    customer_id: int
    table_id: int
    slot_datetime: datetime
    party_size: int
    special_requests: str | None
    status: Literal["confirmed", "cancelled", "completed"]
    created_at: datetime


class Order(DomainModel):
    id: int
    reservation_id: int
    menu_item_id: int
    quantity: int = Field(gt=0)
    created_at: datetime


class ToolResult(DomainModel):
    ok: bool
    data: Any = None
    error_code: str | None = None
    message: str
