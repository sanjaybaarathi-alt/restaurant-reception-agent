"""Unit tests for customer-scoped domain tools."""

from datetime import datetime, timedelta
from typing import Any

import pytest

from src.models.domain import Availability, AvailableTable, Customer, MenuItem, Order, Reservation
from src.tools import build_restaurant_tools


def customer() -> Customer:
    return Customer(
        id=3,
        name="Anita",
        phone="12345678",
        email=None,
        preferences={"allergies": ["nuts"]},
        created_at=datetime.now(),
    )


def reservation(customer_id: int = 3) -> Reservation:
    return Reservation(
        id=9,
        customer_id=customer_id,
        table_id=7,
        slot_datetime=datetime.now() + timedelta(days=1),
        party_size=3,
        special_requests=None,
        status="confirmed",
        created_at=datetime.now(),
    )


class FakeClient:
    def __init__(self) -> None:
        self.created_payload: dict[str, Any] | None = None
        self.cancelled: int | None = None
        self.preferences: dict[str, Any] | None = None
        self.order_added = False

    async def list_menu(self, **_: Any) -> list[MenuItem]:
        return [
            MenuItem(
                id=1,
                name="Samosa",
                description="Crispy",
                price=150,
                tags=["vegan"],
                category="starter",
                available=True,
            )
        ]

    async def get_menu_item(self, item_id: int) -> MenuItem:
        return (await self.list_menu())[0]

    async def check_availability(self, **_: Any) -> Availability:
        return Availability(
            slot_datetime=datetime.now() + timedelta(days=1),
            party_size=3,
            available_tables=[
                AvailableTable(table_id=8, table_number=8, capacity=8, location="outdoor"),
                AvailableTable(table_id=7, table_number=7, capacity=4, location="outdoor"),
            ],
        )

    async def list_reservations(self, customer_id: int, status: str | None = None) -> list[Reservation]:
        return [reservation(customer_id)]

    async def create_reservation(self, payload: dict[str, Any]) -> Reservation:
        self.created_payload = payload
        return reservation(payload["customer_id"])

    async def cancel_reservation(self, reservation_id: int) -> Reservation:
        self.cancelled = reservation_id
        return reservation()

    async def list_customer_orders(self, customer_id: int) -> list[Order]:
        return [Order(id=1, reservation_id=9, menu_item_id=1, quantity=2, created_at=datetime.now())]

    async def list_reservation_orders(self, reservation_id: int) -> list[Order]:
        return [Order(id=1, reservation_id=reservation_id, menu_item_id=1, quantity=2, created_at=datetime.now())]

    async def add_order(self, reservation_id: int, menu_item_id: int, quantity: int) -> Order:
        self.order_added = True
        return Order(
            id=2,
            reservation_id=reservation_id,
            menu_item_id=menu_item_id,
            quantity=quantity,
            created_at=datetime.now(),
        )

    async def remove_order(self, order_id: int) -> None:
        return None

    async def get_customer(self, customer_id: int) -> Customer:
        return customer()

    async def update_preferences(self, customer_id: int, preferences: dict[str, Any]) -> Customer:
        self.preferences = preferences
        updated = customer()
        updated.preferences.update(preferences)
        return updated


def tools_by_name(client: FakeClient) -> dict[str, Any]:
    return {item.name: item for item in build_restaurant_tools(client, 3)}  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_availability_is_sorted_by_smallest_fit() -> None:
    result = await tools_by_name(FakeClient())["check_availability"].ainvoke(
        {"slot_datetime": (datetime.now() + timedelta(days=1)).isoformat(), "party_size": 3, "location": "outdoor"}
    )
    assert result["data"]["available_tables"][0]["table_id"] == 7


@pytest.mark.asyncio
async def test_customer_id_is_injected_for_booking() -> None:
    client = FakeClient()
    await tools_by_name(client)["create_reservation"].ainvoke(
        {"table_id": 7, "slot_datetime": (datetime.now() + timedelta(days=1)).isoformat(), "party_size": 3}
    )
    assert client.created_payload is not None
    assert client.created_payload["customer_id"] == 3


@pytest.mark.asyncio
async def test_cross_customer_cancellation_is_denied() -> None:
    client = FakeClient()
    result = await tools_by_name(client)["cancel_reservation"].ainvoke({"reservation_id": 404})
    assert result["ok"] is False
    assert result["error_code"] == "OWNERSHIP_DENIED"
    assert client.cancelled is None


@pytest.mark.asyncio
async def test_history_resolves_menu_item_name() -> None:
    result = await tools_by_name(FakeClient())["list_my_order_history"].ainvoke({})
    assert result["data"][0]["menu_item_name"] == "Samosa"


@pytest.mark.asyncio
async def test_preferences_are_deduplicated() -> None:
    client = FakeClient()
    result = await tools_by_name(client)["remember_preferences"].ainvoke(
        {"seating": "outdoor", "dietary": ["vegetarian", "vegetarian"], "allergies": ["nuts"]}
    )
    assert result["ok"] is True
    assert client.preferences == {"seating": "outdoor", "dietary": ["vegetarian"], "allergies": ["nuts"]}


@pytest.mark.asyncio
async def test_read_and_write_tools_complete_happy_paths() -> None:
    client = FakeClient()
    tools = tools_by_name(client)
    menu_result = await tools["list_menu"].ainvoke({"category": "starter", "max_price": 400})
    reservations_result = await tools["list_my_reservations"].ainvoke({"status": "confirmed"})
    orders_result = await tools["list_reservation_orders"].ainvoke({"reservation_id": 9})
    add_result = await tools["add_order_item"].ainvoke({"reservation_id": 9, "menu_item_id": 1, "quantity": 2})
    remove_result = await tools["remove_order_item"].ainvoke({"reservation_id": 9, "order_id": 1})
    cancel_result = await tools["cancel_reservation"].ainvoke({"reservation_id": 9})
    unchanged = await tools["remember_preferences"].ainvoke({})

    assert menu_result["ok"] is True
    assert reservations_result["data"][0]["id"] == 9
    assert orders_result["data"][0]["quantity"] == 2
    assert add_result["data"]["menu_item_id"] == 1
    assert remove_result["data"]["order_id"] == 1
    assert cancel_result["ok"] is True
    assert unchanged["message"] == "No preference changes were requested."


@pytest.mark.asyncio
async def test_order_ownership_checks_block_wrong_ids() -> None:
    tools = tools_by_name(FakeClient())
    listed = await tools["list_reservation_orders"].ainvoke({"reservation_id": 404})
    added = await tools["add_order_item"].ainvoke({"reservation_id": 404, "menu_item_id": 1, "quantity": 1})
    removed = await tools["remove_order_item"].ainvoke({"reservation_id": 9, "order_id": 404})
    assert listed["error_code"] == "OWNERSHIP_DENIED"
    assert added["error_code"] == "OWNERSHIP_DENIED"
    assert removed["error_code"] == "OWNERSHIP_DENIED"


@pytest.mark.asyncio
async def test_saved_allergy_blocks_order_before_backend_mutation() -> None:
    class NutClient(FakeClient):
        async def get_menu_item(self, item_id: int) -> MenuItem:
            return MenuItem(
                id=item_id,
                name="Kulfi",
                description="Frozen dessert",
                price=250,
                tags=["contains-nuts", "contains-dairy"],
                category="dessert",
                available=True,
            )

    client = NutClient()
    result = await tools_by_name(client)["add_order_item"].ainvoke(
        {"reservation_id": 9, "menu_item_id": 12, "quantity": 1}
    )
    assert result["error_code"] == "ALLERGEN_CONFLICT"
    assert client.order_added is False


@pytest.mark.asyncio
async def test_booking_recheck_blocks_stale_table_selection() -> None:
    class UnavailableClient(FakeClient):
        async def check_availability(self, **_: Any) -> Availability:
            return Availability(
                slot_datetime=datetime.now() + timedelta(days=1),
                party_size=3,
                available_tables=[],
            )

    client = UnavailableClient()
    result = await tools_by_name(client)["create_reservation"].ainvoke(
        {"table_id": 7, "slot_datetime": (datetime.now() + timedelta(days=1)).isoformat(), "party_size": 3}
    )
    assert result["error_code"] == "TABLE_NO_LONGER_AVAILABLE"
    assert client.created_payload is None
