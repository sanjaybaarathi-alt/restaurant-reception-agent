"""FastAPI application entrypoint."""
from fastapi import FastAPI

from app.database import Base, engine
from app.routers import (
    availability,
    customers,
    menu,
    orders,
    reservations,
    tables,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Restaurant Reservation API",
    version="1.0.0",
    description=(
        "Backend service for the restaurant reception agent exercise. "
        "Provides tables, menu, reservations, orders, and customer "
        "profile data. Treat this as a black box and do not modify it."
    ),
)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.include_router(tables.router)
app.include_router(customers.router)
app.include_router(menu.router)
app.include_router(reservations.router)
app.include_router(orders.router)
app.include_router(availability.router)
