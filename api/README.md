# Restaurant Reception Agent API Contract

The public agent API is defined in [restaurant-agent.openapi.yaml](restaurant-agent.openapi.yaml).
It intentionally exposes only session creation, conversational turns, and health. Restaurant
operations remain behind typed internal tools that call the supplied backend over HTTP.

## Identity and sessions

- `POST /v1/sessions` requires phone or email and performs deterministic lookup before the LLM is involved.
- A missing customer is created only when a non-empty name is also supplied. Otherwise the caller receives a validation error asking for the name.
- If phone and email resolve to different records, session creation fails with `IDENTITY_CONFLICT`; records are never guessed or merged.
- Session state is persisted in `restaurant-agent/data/agent.db` by LangGraph's async SQLite checkpointer using the session UUID as `thread_id`. Agent session/idempotency tables use the same local SQLite database through async SQLAlchemy. The process itself remains stateless.
- `client_message_id` makes each conversational turn idempotent. Reusing the key with a different message returns `409`.

## Internal agent tool contract

All arguments and results are validated with Pydantic models. The authenticated `customer_id` and upstream base URL are injected by the service and are never accepted from model-generated arguments.

| Tool | Model-supplied arguments | Upstream operation | Notes |
|---|---|---|---|
| `list_menu` | `category?`, `tags_any?`, `tags_all?`, `exclude_tags?`, `max_price?`, `available_only=true` | `GET /menu` | Used for menu enquiries, item resolution, and safe recommendations. |
| `check_availability` | `slot_datetime`, `party_size`, `location?` | `GET /availability` | Datetime is resolved to restaurant-local ISO 8601 before dispatch. |
| `list_my_reservations` | `status?` | `GET /customers/{customer_id}/reservations` | Customer ID is injected. |
| `get_reservation` | `reservation_id` | `GET /reservations/{id}` | Service verifies ownership against the session customer before returning data. |
| `create_reservation` | `table_id`, `slot_datetime`, `party_size`, `special_requests?` | `POST /reservations` | Customer ID is injected; availability must be checked in the same turn immediately beforehand. |
| `cancel_reservation` | `reservation_id` | `DELETE /reservations/{id}` | Ownership is checked before mutation. Ambiguous references require clarification. |
| `list_my_order_history` | none | `GET /customers/{customer_id}/orders`, then `GET /menu/{id}` as needed | Resolves menu names and groups records by reservation/date. |
| `list_reservation_orders` | `reservation_id` | `GET /reservations/{id}/orders` | Ownership is checked before access. |
| `add_order_item` | `reservation_id`, `menu_item_id`, `quantity` | `POST /reservations/{id}/orders` | Ownership and menu/dietary constraints are checked before mutation. |
| `remove_order_item` | `reservation_id`, `order_id` | `DELETE /orders/{id}` | Reservation and order ownership are checked before mutation. |
| `remember_preferences` | `seating?`, `dietary?`, `allergies?` | `PATCH /customers/{id}/preferences` | Called only for explicit durable preferences; unknown existing keys are preserved. |

Unknown tool names are rejected without HTTP dispatch and returned to the loop as a structured `UNKNOWN_TOOL` observation. Malformed arguments produce a structured `INVALID_TOOL_ARGUMENTS` observation with safe field-level validation details. Neither condition crashes the turn. The loop permits at most eight model steps and six mutating calls per turn; reaching a limit returns a deterministic failure response and records an audit event.

## Human-in-the-loop confirmation

The LangGraph workflow checkpoints before an inferred destructive cancellation or order removal when the current message did not explicitly identify and request that action. The API returns `status: needs_input` with a confirmation question. The next message for the same session resumes the checkpoint using LangGraph `Command(resume=...)`. Explicit, unambiguous destructive requests proceed without redundant confirmation. Read operations, bookings, and order additions do not use this interrupt.

## Local test interface

`GET /` returns a static single-page HTML interface served by FastAPI. It collects name, phone, and email, starts a session, displays the conversation, generates a unique `client_message_id` for each turn, and renders pending confirmation questions like normal assistant messages. It contains no business logic and communicates only through the documented REST endpoints.

The page also shows active customer/session context, offers example prompts, prevents duplicate sends while a request is pending, preserves a failed message for retry, announces status changes accessibly, and supports starting a clean session. These are presentation behaviors only and do not change the REST schema.

## Booking completeness contract

Before `check_availability` or `create_reservation` can execute, the workflow must have a resolved party size, exact restaurant-local date/time, and seating decision. A current-turn indoor/outdoor choice takes precedence over a saved preference. A saved preference may satisfy the location for a returning customer. If neither exists, the agent asks the customer to choose indoor, outdoor, or explicitly accept either; omission is not interpreted as no preference.

Partial booking answers persist in LangGraph session state. After every answer, a deterministic booking guard recomputes all missing fields and asks one concise clarification covering what remains. Premature availability or reservation tool calls are blocked without upstream dispatch. An explicit “either”, “anywhere”, or “no preference” allows an unfiltered availability search but is not stored as a durable preference.

## Streaming conversation contract

`POST /v1/sessions/{session_id}/messages/stream` accepts the existing `MessageRequest` and returns `text/event-stream`. The React client consumes it using `fetch` plus `ReadableStream`, since browser `EventSource` cannot send the required JSON POST body. Events use standard `event: <type>` and `data: <compact-json>` frames.

- `status`: safe phases `accepted`, `thinking`, `using_tool`, or `composing`; it may contain only a public tool name.
- `delta`: an append-only assistant text fragment.
- `complete`: the canonical persisted `MessageResponse`.
- `error`: the existing public `ErrorResponse`, after which the stream closes.
- `: heartbeat`: an optional comment frame used to avoid idle proxy timeouts.

The streaming and JSON endpoints share `(session_id, client_message_id)` idempotency. Reconnect and retry reuse the original ID. The stream never exposes chain-of-thought, prompts, tool arguments, customer PII, or provider payloads. Client disconnect cancels work where safe; completed backend mutations stay persisted and are not repeated.

## Portfolio frontend

The frontend becomes an independent `frontend/` React + TypeScript project built with Vite. Development runs on port `5173` with API paths proxied to FastAPI on `8080`; the production Docker build emits assets served by FastAPI at `/`. The interface is chat-first after compact identity onboarding and includes streaming text, safe progress states, quick prompts, retry/reconnect behavior, responsive mobile layout, keyboard support, accessible live regions, and polished empty and error states. No provider key or restaurant business rule enters the browser bundle.

## Tool documentation contract

Every model-visible tool docstring must state its purpose, all model-supplied arguments and allowed values, required preconditions, read/write side effects, success result semantics, expected business failures, and identity/ownership behavior. Descriptions must tell the model when to ask the customer for clarification and must not duplicate implementation-only details or expose the upstream base URL. Docstrings and Pydantic/typing annotations together are the tool schema passed to Groq.

## Durable customer preference schema

The existing seeded keys are canonical:

```json
{
  "seating": "indoor | outdoor",
  "dietary": ["vegetarian", "vegan"],
  "allergies": ["nuts", "dairy"]
}
```

The application maps `allergies: ["nuts"]` to menu exclusion tag `contains-nuts` (and similarly for dairy). It reads and preserves unknown keys. It writes a preference only when the customer explicitly states a stable preference or allergy; a one-off request applies to the current turn/reservation but is not persisted. Because the upstream endpoint shallow-merges top-level keys, an updated list replaces that complete list after merging and de-duplicating it locally.

## Error semantics

Expected restaurant business-rule errors are supplied to the agent as structured observations so it can explain the issue and offer a valid next step. Public responses never include raw exception text, provider payloads, hidden prompts, or chain-of-thought. Transport failures, timeouts, invalid upstream schemas, and exhausted LLM repair attempts use stable application error codes and a correlation `trace_id`.
