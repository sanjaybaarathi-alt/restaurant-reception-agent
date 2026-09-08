"""SQLAlchemy ORM models."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Table(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)
    table_number = Column(Integer, unique=True, nullable=False, index=True)
    capacity = Column(Integer, nullable=False)
    location = Column(String, nullable=False)  # 'indoor' | 'outdoor'

    reservations = relationship("Reservation", back_populates="table")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    preferences = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    reservations = relationship("Reservation", back_populates="customer")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    category = Column(String, nullable=False)  # 'starter' | 'main' | 'dessert'
    available = Column(Boolean, default=True, nullable=False)

    orders = relationship("Order", back_populates="menu_item")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=False)
    slot_datetime = Column(DateTime, nullable=False, index=True)
    party_size = Column(Integer, nullable=False)
    special_requests = Column(String, nullable=True)
    status = Column(String, default="confirmed", nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    customer = relationship("Customer", back_populates="reservations")
    table = relationship("Table", back_populates="reservations")
    orders = relationship(
        "Order", back_populates="reservation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_reservation_table_slot", "table_id", "slot_datetime"),
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(
        Integer,
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
    )
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    reservation = relationship("Reservation", back_populates="orders")
    menu_item = relationship("MenuItem", back_populates="orders")
