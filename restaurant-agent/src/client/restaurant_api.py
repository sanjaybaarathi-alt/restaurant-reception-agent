"""Typed asynchronous client for the supplied Restaurant Reservation API."""

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from src.models.domain import Availability, Customer, MenuItem, Order, Reservation
from src.utils.exceptions import UpstreamError, error_codes

ModelT = TypeVar("ModelT", bound=BaseModel)


class RestaurantApiClient:
    """The only component permitted to call the supplied backend."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def health(self) -> bool:
        try:
            response = await self._client.get("/health")
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    async def lookup_customer(self, *, phone: str | None = None, email: str | None = None) -> Customer | None:
        params = {key: value for key, value in {"phone": phone, "email": email}.items() if value}
        response = await self._request("GET", "/customers/lookup", params=params, allow_not_found=True)
        return None if response is None else self._parse(Customer, response)

    async def create_customer(
        self, *, name: str, phone: str | None, email: str | None, preferences: dict[str, Any] | None = None
    ) -> Customer:
        response = await self._request(
            "POST",
            "/customers",
            json={"name": name, "phone": phone, "email": email, "preferences": preferences or {}},
        )
        return self._parse(Customer, response)

    async def get_customer(self, customer_id: int) -> Customer:
        return self._parse(Customer, await self._request("GET", f"/customers/{customer_id}"))

    async def update_preferences(self, customer_id: int, preferences: dict[str, Any]) -> Customer:
        response = await self._request(
            "PATCH", f"/customers/{customer_id}/preferences", json={"preferences": preferences}
        )
        return self._parse(Customer, response)

    async def list_menu(self, **filters: Any) -> list[MenuItem]:
        params = {key: value for key, value in filters.items() if value is not None}
        return self._parse_list(MenuItem, await self._request("GET", "/menu", params=params))

    async def get_menu_item(self, item_id: int) -> MenuItem:
        return self._parse(MenuItem, await self._request("GET", f"/menu/{item_id}"))

    async def check_availability(self, *, slot_datetime: str, party_size: int, location: str | None) -> Availability:
        params = {"slot_datetime": slot_datetime, "party_size": party_size}
        if location:
            params["location"] = location
        return self._parse(Availability, await self._request("GET", "/availability", params=params))

    async def list_reservations(self, customer_id: int, status: str | None = None) -> list[Reservation]:
        params = {"status": status} if status else None
        response = await self._request("GET", f"/customers/{customer_id}/reservations", params=params)
        return self._parse_list(Reservation, response)

    async def get_reservation(self, reservation_id: int) -> Reservation:
        return self._parse(Reservation, await self._request("GET", f"/reservations/{reservation_id}"))

    async def create_reservation(self, payload: dict[str, Any]) -> Reservation:
        return self._parse(Reservation, await self._request("POST", "/reservations", json=payload))

    async def cancel_reservation(self, reservation_id: int) -> Reservation:
        return self._parse(Reservation, await self._request("DELETE", f"/reservations/{reservation_id}"))

    async def list_customer_orders(self, customer_id: int) -> list[Order]:
        response = await self._request("GET", f"/customers/{customer_id}/orders")
        return self._parse_list(Order, response)

    async def list_reservation_orders(self, reservation_id: int) -> list[Order]:
        response = await self._request("GET", f"/reservations/{reservation_id}/orders")
        return self._parse_list(Order, response)

    async def add_order(self, reservation_id: int, menu_item_id: int, quantity: int) -> Order:
        response = await self._request(
            "POST",
            f"/reservations/{reservation_id}/orders",
            json={"menu_item_id": menu_item_id, "quantity": quantity},
        )
        return self._parse(Order, response)

    async def remove_order(self, order_id: int) -> None:
        await self._request("DELETE", f"/orders/{order_id}", expect_empty=True)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
        expect_empty: bool = False,
    ) -> Any:
        try:
            response = await self._client.request(method, path, params=params, json=json)
        except httpx.TimeoutException as exc:
            raise UpstreamError(
                error_codes.UPSTREAM_UNAVAILABLE, "The restaurant service timed out. Please try again.", 503, True
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(
                error_codes.UPSTREAM_UNAVAILABLE, "The restaurant service is unavailable. Please try again.", 503, True
            ) from exc
        if allow_not_found and response.status_code == 404:
            return None
        if response.is_error:
            detail = self._safe_detail(response)
            raise UpstreamError(error_codes.UPSTREAM_ERROR, detail, 502, response.status_code >= 500)
        if expect_empty:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(error_codes.UPSTREAM_ERROR, "The restaurant service returned invalid data.") from exc

    @staticmethod
    def _safe_detail(response: httpx.Response) -> str:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, str) and response.status_code in {400, 404, 409, 422}:
            return detail[:300]
        return "The restaurant service could not complete that request."

    @staticmethod
    def _parse(model: type[ModelT], data: Any) -> ModelT:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise UpstreamError(error_codes.UPSTREAM_ERROR, "The restaurant service returned invalid data.") from exc

    @staticmethod
    def _parse_list(model: type[ModelT], data: Any) -> list[ModelT]:
        try:
            return TypeAdapter(list[model]).validate_python(data)  # type: ignore[valid-type]
        except ValidationError as exc:
            raise UpstreamError(error_codes.UPSTREAM_ERROR, "The restaurant service returned invalid data.") from exc
