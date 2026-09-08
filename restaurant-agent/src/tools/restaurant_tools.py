"""Typed, customer-scoped tools exposed to the LangGraph model."""

from datetime import datetime
from typing import Annotated, Literal

from langchain_core.tools import BaseTool, tool

from src.client import RestaurantApiClient
from src.models.domain import Reservation, ToolResult
from src.utils.exceptions import UpstreamError, error_codes

Category = Literal["starter", "main", "dessert"]
Location = Literal["indoor", "outdoor"]
ReservationStatus = Literal["confirmed", "cancelled", "completed"]


def _success(data: object, message: str) -> dict[str, object]:
    return ToolResult(ok=True, data=data, message=message).model_dump(mode="json")


def _failure(exc: UpstreamError) -> dict[str, object]:
    return ToolResult(ok=False, error_code=exc.code, message=exc.message).model_dump(mode="json")


async def _owned_reservation(client: RestaurantApiClient, customer_id: int, reservation_id: int) -> Reservation | None:
    reservations = await client.list_reservations(customer_id)
    return next((item for item in reservations if item.id == reservation_id), None)


def build_restaurant_tools(client: RestaurantApiClient, customer_id: int) -> list[BaseTool]:
    """Build tools whose customer identity cannot be overridden by model arguments."""

    @tool
    async def list_menu(
        category: Annotated[Category | None, "starter, main, or dessert"] = None,
        tags_any: Annotated[list[str] | None, "include items with any tag"] = None,
        tags_all: Annotated[list[str] | None, "include items with all tags"] = None,
        exclude_tags: Annotated[list[str] | None, "exclude items with any tag"] = None,
        max_price: Annotated[float | None, "maximum item price, inclusive"] = None,
        available_only: Annotated[bool, "exclude unavailable items"] = True,
    ) -> dict[str, object]:
        """Search the restaurant menu before recommending or ordering food.

        Args: category accepts starter, main, or dessert. Tag filters accept menu tag
        strings; ``tags_any`` matches at least one, ``tags_all`` requires every tag,
        and ``exclude_tags`` removes conflicts. ``max_price`` is inclusive and
        ``available_only`` defaults to true. Clarify unknown dietary terms instead of
        inventing tags. This read-only tool returns ``ToolResult`` with matching menu
        records on success, or an upstream error code/message without side effects.
        """
        try:
            items = await client.list_menu(
                category=category,
                tags_any=tags_any,
                tags_all=tags_all,
                exclude_tags=exclude_tags,
                max_price=max_price,
                available_only=available_only,
            )
            return _success([item.model_dump(mode="json") for item in items], f"Found {len(items)} menu items.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def check_availability(
        slot_datetime: Annotated[datetime, "naive restaurant-local date and time"],
        party_size: Annotated[int, "positive number of guests"],
        location: Annotated[Location | None, "preferred seating location"] = None,
    ) -> dict[str, object]:
        """Find tables for an exact restaurant-local date, time, and party size.

        Args: ``slot_datetime`` must be a resolved local datetime, ``party_size`` must
        be positive, and ``location`` is optional indoor/outdoor seating. Ask the user
        to clarify ambiguous dates, times, party sizes, or locations before calling.
        This read-only tool returns available tables sorted by smallest fit, then table
        number. Expected failures are returned as structured upstream errors; it makes
        no reservation and has no side effects.
        """
        try:
            result = await client.check_availability(
                slot_datetime=slot_datetime.replace(tzinfo=None).isoformat(), party_size=party_size, location=location
            )
            tables = sorted(result.available_tables, key=lambda item: (item.capacity, item.table_number))
            data = result.model_dump(mode="json")
            data["available_tables"] = [item.model_dump(mode="json") for item in tables]
            return _success(data, f"Found {len(tables)} available tables; the first is the smallest fit.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def list_my_reservations(status: ReservationStatus | None = None) -> dict[str, object]:
        """List reservations owned by the customer bound to this conversation.

        Args: optional ``status`` accepts confirmed, cancelled, or completed. Customer
        identity is injected by the application and cannot be supplied or overridden
        by the model. Use this read-only tool when a reservation ID or current booking
        must be established. It returns owned reservations or a structured upstream
        error and never exposes another customer's records.
        """
        try:
            items = await client.list_reservations(customer_id, status)
            return _success([item.model_dump(mode="json") for item in items], f"Found {len(items)} reservations.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def create_reservation(
        table_id: Annotated[int, "table_id returned by the immediately preceding availability check"],
        slot_datetime: Annotated[datetime, "exact naive restaurant-local slot"],
        party_size: Annotated[int, "positive number of guests"],
        special_requests: str | None = None,
    ) -> dict[str, object]:
        """Create a reservation for the customer bound to this conversation.

        Args: ``table_id`` must come from availability for the exact resolved
        ``slot_datetime`` and positive ``party_size``; ``special_requests`` is optional.
        Clarify any missing or ambiguous booking detail first. The tool rechecks table
        availability immediately, then creates the booking as a side effect. Customer
        identity is injected and cannot be overridden. Success returns the reservation;
        expected errors include stale availability and structured upstream failures.
        """
        try:
            availability = await client.check_availability(
                slot_datetime=slot_datetime.replace(tzinfo=None).isoformat(),
                party_size=party_size,
                location=None,
            )
            if not any(table.table_id == table_id for table in availability.available_tables):
                return ToolResult(
                    ok=False,
                    error_code=error_codes.TABLE_NO_LONGER_AVAILABLE,
                    message="That table is no longer available for the requested slot.",
                ).model_dump(mode="json")
            item = await client.create_reservation(
                {
                    "customer_id": customer_id,
                    "table_id": table_id,
                    "slot_datetime": slot_datetime.replace(tzinfo=None).isoformat(),
                    "party_size": party_size,
                    "special_requests": special_requests,
                }
            )
            return _success(item.model_dump(mode="json"), f"Reservation {item.id} was created.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def cancel_reservation(reservation_id: int) -> dict[str, object]:
        """Cancel a confirmed reservation owned by the bound customer.

        Args: ``reservation_id`` must identify the intended booking; list reservations
        or clarify when the user has not identified one. This destructive call changes
        reservation status. Use it only after an explicit cancellation request or the
        graph's human confirmation. Ownership is checked before mutation. Success
        returns the cancelled reservation; ownership denial and upstream conflicts are
        returned as structured errors.
        """
        try:
            if await _owned_reservation(client, customer_id, reservation_id) is None:
                return ToolResult(
                    ok=False,
                    error_code=error_codes.OWNERSHIP_DENIED,
                    message="That reservation does not belong to this customer.",
                ).model_dump(mode="json")
            item = await client.cancel_reservation(reservation_id)
            return _success(item.model_dump(mode="json"), f"Reservation {item.id} was cancelled.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def list_my_order_history() -> dict[str, object]:
        """Retrieve order history for the customer bound to this conversation.

        This tool has no arguments and is read-only. Use it to answer order-history or
        past-preference questions, not to inspect arbitrary customers. Identity is
        injected by the application and cannot be overridden. Success returns order
        lines with resolved menu item names; missing old menu items are labelled
        unknown, and upstream failures are returned as structured errors.
        """
        try:
            orders = await client.list_customer_orders(customer_id)
            menu = {item.id: item for item in await client.list_menu(available_only=False)}
            resolved = []
            for order in orders:
                menu_item = menu.get(order.menu_item_id)
                resolved.append(
                    {
                        **order.model_dump(mode="json"),
                        "menu_item_name": menu_item.name if menu_item else "Unknown item",
                    }
                )
            return _success(resolved, f"Found {len(resolved)} historical order lines.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def list_reservation_orders(reservation_id: int) -> dict[str, object]:
        """List current order lines for one customer-owned reservation.

        Args: ``reservation_id`` must refer to the booking being discussed; clarify or
        list reservations if it is unknown. The operation is read-only. Customer
        ownership is verified before orders are fetched, so another customer's orders
        are never returned. Success contains the order lines; ownership denial and
        upstream failures use structured error codes and messages.
        """
        try:
            if await _owned_reservation(client, customer_id, reservation_id) is None:
                return ToolResult(
                    ok=False, error_code=error_codes.OWNERSHIP_DENIED, message="Reservation access denied."
                ).model_dump(mode="json")
            orders = await client.list_reservation_orders(reservation_id)
            return _success([item.model_dump(mode="json") for item in orders], f"Found {len(orders)} order lines.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def add_order_item(reservation_id: int, menu_item_id: int, quantity: int) -> dict[str, object]:
        """Add a menu item to a customer-owned reservation as a side effect.

        Args: ``reservation_id`` identifies the booking, ``menu_item_id`` must come from
        the menu, and ``quantity`` must be positive. Clarify uncertain items, quantities,
        or bookings first. Ownership is checked and the customer's stored allergies are
        compared with menu tags before mutation. Success returns the new order line;
        expected failures include ownership denial, allergen conflict, unavailable
        items, invalid reservation state, and structured upstream errors.
        """
        try:
            if await _owned_reservation(client, customer_id, reservation_id) is None:
                return ToolResult(
                    ok=False, error_code=error_codes.OWNERSHIP_DENIED, message="Reservation access denied."
                ).model_dump(mode="json")
            customer = await client.get_customer(customer_id)
            menu_item = await client.get_menu_item(menu_item_id)
            excluded_tags = {f"contains-{allergy.lower()}" for allergy in customer.preferences.get("allergies", [])}
            conflicts = excluded_tags.intersection(menu_item.tags)
            if conflicts:
                return ToolResult(
                    ok=False,
                    error_code=error_codes.ALLERGEN_CONFLICT,
                    message=f"{menu_item.name} is tagged with {', '.join(sorted(conflicts))}.",
                ).model_dump(mode="json")
            order = await client.add_order(reservation_id, menu_item_id, quantity)
            return _success(order.model_dump(mode="json"), f"Order line {order.id} was added.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def remove_order_item(reservation_id: int, order_id: int) -> dict[str, object]:
        """Remove one order line from a customer-owned reservation.

        Args: ``reservation_id`` and ``order_id`` must unambiguously identify the item;
        list current orders or clarify first when needed. This destructive operation
        should run only after an explicit removal request or the graph's human
        confirmation. Both reservation and order ownership are verified before deletion.
        Success returns the removed ID; ownership denial and upstream conflicts are
        returned as structured errors.
        """
        try:
            if await _owned_reservation(client, customer_id, reservation_id) is None:
                return ToolResult(
                    ok=False, error_code=error_codes.OWNERSHIP_DENIED, message="Reservation access denied."
                ).model_dump(mode="json")
            orders = await client.list_reservation_orders(reservation_id)
            if not any(item.id == order_id for item in orders):
                return ToolResult(
                    ok=False, error_code=error_codes.OWNERSHIP_DENIED, message="Order access denied."
                ).model_dump(mode="json")
            await client.remove_order(order_id)
            return _success({"order_id": order_id}, f"Order line {order_id} was removed.")
        except UpstreamError as exc:
            return _failure(exc)

    @tool
    async def remember_preferences(
        seating: Location | None = None,
        dietary: list[str] | None = None,
        allergies: list[str] | None = None,
    ) -> dict[str, object]:
        """Persist explicitly stated durable preferences for the bound customer.

        Args: ``seating`` accepts indoor/outdoor; ``dietary`` and ``allergies`` are lists
        of user-stated terms. Never infer medical allergies or durable preferences from
        a single order; clarify uncertain intent. This call updates only supplied fields,
        deduplicates list values, and preserves other preferences. Identity is injected.
        Success returns the updated preferences (or unchanged data when no fields are
        supplied); upstream failures are returned as structured errors.
        """
        try:
            current = await client.get_customer(customer_id)
            updates: dict[str, object] = {}
            if seating is not None:
                updates["seating"] = seating
            if dietary is not None:
                updates["dietary"] = sorted(set(dietary))
            if allergies is not None:
                updates["allergies"] = sorted(set(allergies))
            if not updates:
                return _success(current.preferences, "No preference changes were requested.")
            updated = await client.update_preferences(customer_id, updates)
            return _success(updated.preferences, "Customer preferences were updated.")
        except UpstreamError as exc:
            return _failure(exc)

    return [
        list_menu,
        check_availability,
        list_my_reservations,
        create_reservation,
        cancel_reservation,
        list_my_order_history,
        list_reservation_orders,
        add_order_item,
        remove_order_item,
        remember_preferences,
    ]
