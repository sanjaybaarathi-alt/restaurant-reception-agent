"""Seed sample data. Idempotent — does nothing if data already exists.

Usage:
    python -m app.seed              # seed if empty
    python -m app.seed --reset      # wipe and reseed
"""
import sys
from datetime import datetime, timedelta

from app import models
from app.database import Base, SessionLocal, engine


def _floor_to_slot(dt: datetime) -> datetime:
    """Round down to the nearest 30-min slot, between 12:00 and 22:30."""
    minute = 0 if dt.minute < 30 else 30
    out = dt.replace(minute=minute, second=0, microsecond=0)
    if out.hour < 12:
        out = out.replace(hour=12, minute=0)
    if out.hour > 22 or (out.hour == 22 and out.minute > 30):
        out = out.replace(hour=22, minute=30)
    return out


def seed(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if reset:
            print("Resetting all data...")
            db.query(models.Order).delete()
            db.query(models.Reservation).delete()
            db.query(models.MenuItem).delete()
            db.query(models.Customer).delete()
            db.query(models.Table).delete()
            db.commit()

        if db.query(models.Table).count() > 0:
            print("Data already seeded. Use --reset to reseed.")
            return

        tables = [
            models.Table(table_number=1, capacity=2, location="indoor"),
            models.Table(table_number=2, capacity=2, location="indoor"),
            models.Table(table_number=3, capacity=4, location="indoor"),
            models.Table(table_number=4, capacity=4, location="indoor"),
            models.Table(table_number=5, capacity=6, location="indoor"),
            models.Table(table_number=6, capacity=2, location="outdoor"),
            models.Table(table_number=7, capacity=4, location="outdoor"),
            models.Table(table_number=8, capacity=8, location="outdoor"),
        ]
        db.add_all(tables)

        menu = [
            models.MenuItem(
                name="Paneer Tikka",
                description="Charcoal-grilled cottage cheese cubes marinated in spiced yogurt.",
                price=350,
                tags=["vegetarian", "contains-dairy"],
                category="starter",
                available=True,
            ),
            models.MenuItem(
                name="Hara Bhara Kabab",
                description="Spinach, peas, and potato patties, lightly fried.",
                price=300,
                tags=["vegetarian", "vegan"],
                category="starter",
                available=True,
            ),
            models.MenuItem(
                name="Chicken Tikka",
                description="Boneless chicken pieces marinated in yogurt and spices, tandoor-grilled.",
                price=450,
                tags=["contains-dairy"],
                category="starter",
                available=True,
            ),
            models.MenuItem(
                name="Samosa",
                description="Crispy pastry stuffed with spiced potatoes and peas.",
                price=150,
                tags=["vegetarian", "vegan"],
                category="starter",
                available=True,
            ),
            models.MenuItem(
                name="Dal Makhani",
                description="Slow-cooked black lentils in a rich tomato-cream gravy.",
                price=400,
                tags=["vegetarian", "contains-dairy"],
                category="main",
                available=True,
            ),
            models.MenuItem(
                name="Butter Chicken",
                description="Tandoor chicken in a velvety tomato-butter sauce with cashews.",
                price=550,
                tags=["contains-nuts", "contains-dairy"],
                category="main",
                available=True,
            ),
            models.MenuItem(
                name="Paneer Butter Masala",
                description="Paneer in tomato-cashew gravy.",
                price=450,
                tags=["vegetarian", "contains-nuts", "contains-dairy"],
                category="main",
                available=True,
            ),
            models.MenuItem(
                name="Veg Biryani",
                description="Basmati rice cooked with vegetables and aromatic spices.",
                price=400,
                tags=["vegetarian"],
                category="main",
                available=True,
            ),
            models.MenuItem(
                name="Chicken Biryani",
                description="Basmati rice layered with marinated chicken and saffron.",
                price=500,
                tags=[],
                category="main",
                available=True,
            ),
            models.MenuItem(
                name="Roti",
                description="Whole wheat flatbread.",
                price=50,
                tags=["vegetarian", "vegan"],
                category="main",
                available=True,
            ),
            models.MenuItem(
                name="Gulab Jamun",
                description="Deep-fried milk dumplings soaked in rose-cardamom syrup.",
                price=200,
                tags=["vegetarian", "contains-dairy"],
                category="dessert",
                available=True,
            ),
            models.MenuItem(
                name="Kulfi",
                description="Traditional Indian frozen dessert with cardamom and pistachios.",
                price=250,
                tags=["vegetarian", "contains-nuts", "contains-dairy"],
                category="dessert",
                available=True,
            ),
        ]
        db.add_all(menu)

        priya = models.Customer(
            name="Priya Sharma",
            phone="+91-9876543210",
            email="priya.sharma@example.com",
            preferences={
                "seating": "outdoor",
                "dietary": ["vegetarian"],
            },
        )
        rahul = models.Customer(
            name="Rahul Verma",
            phone="+91-9876543211",
            email="rahul.v@example.com",
            preferences={},
        )
        anita = models.Customer(
            name="Anita Iyer",
            phone="+91-9876543212",
            email="anita.iyer@example.com",
            preferences={"allergies": ["nuts"]},
        )
        db.add_all([priya, rahul, anita])
        db.commit()

        # Seed Priya with a past reservation and orders, two weeks ago at 8 PM.
        past_slot = _floor_to_slot(
            datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
            - timedelta(days=14)
        )
        outdoor_4 = next(t for t in tables if t.table_number == 7)
        past_res = models.Reservation(
            customer_id=priya.id,
            table_id=outdoor_4.id,
            slot_datetime=past_slot,
            party_size=3,
            status="confirmed",
        )
        db.add(past_res)
        db.commit()
        db.refresh(past_res)

        paneer = next(m for m in menu if m.name == "Paneer Tikka")
        dal = next(m for m in menu if m.name == "Dal Makhani")
        roti = next(m for m in menu if m.name == "Roti")

        db.add_all(
            [
                models.Order(
                    reservation_id=past_res.id,
                    menu_item_id=paneer.id,
                    quantity=1,
                ),
                models.Order(
                    reservation_id=past_res.id,
                    menu_item_id=dal.id,
                    quantity=2,
                ),
                models.Order(
                    reservation_id=past_res.id,
                    menu_item_id=roti.id,
                    quantity=4,
                ),
            ]
        )
        db.commit()

        print(
            f"Seeded {len(tables)} tables, {len(menu)} menu items, "
            "3 customers, and 1 historical reservation."
        )

    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
