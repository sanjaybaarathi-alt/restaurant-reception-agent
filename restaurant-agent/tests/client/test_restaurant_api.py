"""Contract-focused tests for the supplied backend HTTP adapter."""

import httpx
import pytest

from src.client import RestaurantApiClient
from src.utils.exceptions import UpstreamError


@pytest.mark.asyncio
async def test_lookup_customer_returns_none_for_404() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["phone"] == "+91-1"
        return httpx.Response(404, json={"detail": "Customer not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as http:
        assert await RestaurantApiClient(http).lookup_customer(phone="+91-1") is None


@pytest.mark.asyncio
async def test_menu_response_is_typed() -> None:
    payload = [
        {
            "id": 1,
            "name": "Samosa",
            "description": "Crispy",
            "price": 150.0,
            "tags": ["vegetarian", "vegan"],
            "category": "starter",
            "available": True,
        }
    ]

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as http:
        items = await RestaurantApiClient(http).list_menu(max_price=400)
    assert items[0].name == "Samosa"
    assert items[0].price == 150


@pytest.mark.asyncio
async def test_business_error_is_safe_and_actionable() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Cannot cancel within 2 hours of the reservation"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as http:
        with pytest.raises(UpstreamError, match="Cannot cancel within 2 hours"):
            await RestaurantApiClient(http).cancel_reservation(7)


@pytest.mark.asyncio
async def test_invalid_upstream_schema_fails_closed() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as http:
        with pytest.raises(UpstreamError, match="invalid data"):
            await RestaurantApiClient(http).get_customer(1)


@pytest.mark.asyncio
async def test_all_mutation_and_collection_methods_use_expected_contracts() -> None:
    now = "2030-01-01T20:00:00"
    customer_payload = {
        "id": 1,
        "name": "Priya",
        "phone": "+91-1",
        "email": None,
        "preferences": {},
        "created_at": now,
    }
    reservation_payload = {
        "id": 4,
        "customer_id": 1,
        "table_id": 7,
        "slot_datetime": now,
        "party_size": 3,
        "special_requests": None,
        "status": "confirmed",
        "created_at": now,
    }
    order_payload = {
        "id": 8,
        "reservation_id": 4,
        "menu_item_id": 1,
        "quantity": 2,
        "created_at": now,
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(503)
        if path == "/customers" or path.endswith("/preferences") or path == "/customers/1":
            return httpx.Response(200, json=customer_payload)
        if path == "/availability":
            return httpx.Response(
                200,
                json={
                    "slot_datetime": now,
                    "party_size": 3,
                    "available_tables": [{"table_id": 7, "table_number": 7, "capacity": 4, "location": "outdoor"}],
                },
            )
        if path == "/reservations" or path == "/reservations/4":
            return httpx.Response(200, json=reservation_payload)
        if path == "/customers/1/reservations":
            return httpx.Response(200, json=[reservation_payload])
        if path in {"/customers/1/orders", "/reservations/4/orders"}:
            return httpx.Response(200, json=[order_payload] if request.method == "GET" else order_payload)
        if path == "/orders/8":
            return httpx.Response(204)
        raise AssertionError(f"Unexpected path: {path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as http:
        client = RestaurantApiClient(http)
        assert await client.health() is False  # no health route in this focused transport
        assert (await client.create_customer(name="Priya", phone="+91-1", email=None)).id == 1
        assert (await client.get_customer(1)).id == 1
        assert (await client.update_preferences(1, {"seating": "outdoor"})).id == 1
        assert (await client.check_availability(slot_datetime=now, party_size=3, location="outdoor")).party_size == 3
        assert (await client.list_reservations(1, "confirmed"))[0].id == 4
        assert (await client.get_reservation(4)).id == 4
        assert (await client.create_reservation({"customer_id": 1})).id == 4
        assert (await client.list_customer_orders(1))[0].id == 8
        assert (await client.list_reservation_orders(4))[0].id == 8
        assert (await client.add_order(4, 1, 2)).id == 8
        await client.remove_order(8)
