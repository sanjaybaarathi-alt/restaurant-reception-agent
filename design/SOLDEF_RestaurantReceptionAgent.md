## SOLDEF-001-Restaurant Reception Agent

### <u>Project Details</u>
- **Project ID:** PROJ-RA-001
- **Project Name:** Restaurant Reception Agent
- **Story ID:** STORY-001 (assumed; pending user confirmation)
- **Story Name:** Conversational reservations, ordering, menu enquiry, and customer memory
- **Status:** Approved and implemented

### <u> Table of Contents </u>
- [Section 1: Functional Requirements](#section-1-functional-requirements)
  - [1.1 Overview](#11-overview)
  - [1.2 Requirement Details](#12-requirement-details)
  - [1.3 Project Artifacts](#13-project-artifacts)
  - [1.4 Dependencies](#14-dependencies)
- [Section 2: Non Functional Requirements](#section-2-non-functional-requirements)
  - [2.1 Infrastructure and Deployment](#21-infrastructure-and-deployment)
  - [2.2 Architecture and System Design](#22-architecture-and-system-design)
- [Section 3: In Scope and Out Scope](#section-3-in-scope-and-out-scope)
  - [3.1 Inscope Details](#31-inscope-details)
  - [3.2 Outscope Details](#32-outscope-details)
- [Section 4: Solution Diagrams](#section-4-solution-diagrams)

### <u> Section 1: Functional Requirements </u>

#### <u> 1.1 Overview </u>

The Restaurant Reception Agent is a new Python application that sits beside, and does not modify, the supplied `restaurant-api`. It exposes REST and Server-Sent Events conversation interfaces plus a portfolio-quality React chat application through which a customer identifies themself by phone or email and continues a multi-turn natural-language session. Identity resolution occurs deterministically before any model invocation. A bounded tool-using agent then interprets requests about menu items, table availability, reservations, cancellations, pre-orders, order removal, preferences, and previous orders. It may execute multiple typed tools during one turn, using only HTTP calls to the supplied backend.

The solution separates the static test UI, public API handling, agent orchestration, domain services, session persistence, the LLM adapter, and the upstream HTTP client. LangGraph remains the agent framework. A typed `StateGraph` separates context retrieval, model planning, validated tool execution, optional customer confirmation, and response construction, with conditional edges controlling the loop. A local agent-owned SQLite file at `restaurant-agent/data/agent.db` stores LangGraph checkpoints plus session, idempotency, and privacy-safe audit records. Durable customer facts remain in the supplied backend's customer preference JSON; the two memory types are deliberately separate. Groq is the LLM provider through `langchain-groq`, defaulting to the tool-capable `openai/gpt-oss-20b` model and respecting account free-plan limits.

The agent asks focused follow-up questions whenever a required fact or referenced reservation is ambiguous. Booking completeness is enforced by deterministic workflow state rather than prompt compliance alone: availability and reservation tools cannot run until party size, exact restaurant-local date/time, and a seating decision are resolved. A saved seating preference satisfies the seating decision; a new customer or a customer without one must choose indoor, outdoor, or explicitly state that either is acceptable. The agent resolves relative dates in restaurant-local time, applies saved preferences as defaults, filters allergens, chooses the smallest suitable available table, and reports backend business-rule failures honestly. Every tool call is schema-validated, ownership-scoped, observable, and bounded. The browser test client provides clearer session state, suggested actions, pending/failed message feedback, and responsive accessible chat behavior without containing restaurant business logic.

#### <u> 1.2 Requirement Details </u>

- **FRA-001: Identified multi-turn conversation sessions**
- **FRA-002: Bounded typed agent loop**
- **FRA-003: Menu enquiry and personalized recommendations**
- **FRA-004: Availability and reservation management**
- **FRA-005: Reservation order management**
- **FRA-006: Durable customer memory and historical recall**
- **FRA-007: Safe errors, ambiguity handling, and audit output**
- **FRA-008: Streaming portfolio chat interface**

##### <u> 1.2.1 FRA-001: Identified multi-turn conversation sessions </u>

##### Description:
Expose the REST operations in `api/restaurant-agent.openapi.yaml`. `POST /v1/sessions` accepts a phone or email and optional name. The session service looks up the customer in the supplied backend without using the LLM. If no customer exists, it requires a name and creates one. When both phone and email are given, they must identify the same record. A random UUID session is persisted with the backend customer ID and timestamps. `POST /v1/sessions/{session_id}/messages` appends and processes turns.

##### Session state:
Persist customer and assistant messages, validated tool observations needed for context, turn status, trace ID, token counts, and an idempotency record keyed by `(session_id, client_message_id)`. The service process retains no authoritative in-memory session state. On each turn, load the prompt, customer memory, bounded recent conversation history, and current message in that order.

##### Validation and idempotency:
Messages are non-empty and at most 4,000 characters. A duplicate `client_message_id` with the same payload returns the stored response without repeating side effects; reuse with different content returns `409`. Invalid or expired session IDs return a stable typed error. Phone/email normalization is deterministic and documented; raw identifiers are not written to application logs.

##### Acceptance Criteria:
- A known customer can start a session by phone or email and receives a new session UUID.
- A new customer is created only after name and at least one identifier are available.
- Follow-up turns use prior session context without requiring identity again.
- Retrying a completed message cannot create duplicate reservations or orders.
- Session state survives an application process restart.

##### <u> 1.2.2 FRA-002: Bounded typed agent loop </u>

##### Description:
Use one LangGraph workflow with a `TypedDict` state and `Annotated[list, add_messages]` message channel. Its nodes are `retrieve_context`, `call_model`, `confirm_action`, `execute_tools`, and `build_response`. Conditional edges route model tool calls to confirmation or a `ToolNode`, loop typed observations back to the model, and stop on a valid final response or configured limit. The chat model is bound to registered tools with `bind_tools`. The system prompt is stored as versioned YAML and defines role, mission, scope, constraints, rules, workflow, output contract, and error behavior. Domain services and the HTTP client execute operations. The LLM never receives control over base URLs, customer IDs, authorization context, arbitrary HTTP methods, or arbitrary paths.

##### Human-in-the-loop policy:
Use LangGraph `interrupt_before`/`interrupt` with the SQLite checkpointer only when a destructive cancellation or order removal was inferred from context and the current user turn did not explicitly identify and request that action. The response asks for confirmation and returns `needs_input`; the next message resumes the same graph thread with `Command(resume=...)`. Explicit unambiguous customer requests, reads, bookings, and order additions do not require an extra checkpoint. This keeps the flow useful while preventing an inferred destructive action from executing silently.

##### Tool documentation contract:
Every model-visible tool uses a detailed docstring that specifies purpose, arguments and allowed values, preconditions, read/write side effects, success-result meaning, expected business failures, customer ownership scoping, and when clarification is required. Python annotations/Pydantic schemas define the machine-readable argument contract. Docstrings must not expose internal URLs or encourage the model to bypass deterministic validation.

##### Loop behavior:
Each model response is validated before use. Valid tool calls are dispatched, their typed results are appended as observations, and the model decides whether another tool or a final response is needed. Maximum model steps are eight per turn, maximum tool calls are twelve, and maximum mutating calls are six. Unknown tools and invalid arguments become structured failure observations without dispatch. Structured-output repair is capped at two attempts; exhaustion returns a deterministic safe response.

##### Decision rules:
- Ask for missing required facts rather than inventing them.
- Require exact restaurant-local date/time and party size before checking availability.
- Require a seating decision before checking availability: use an explicit current-turn choice, otherwise a saved preference, otherwise ask indoor, outdoor, or either. Never treat omitted seating as “either” for a new customer.
- When several booking facts are missing, ask one concise combined clarification listing every missing fact; retain partial answers across turns and re-evaluate completeness after each reply.
- Check availability immediately before creating a reservation.
- Resolve phrases such as “that reservation” from session state only when exactly one candidate is credible; request confirmation through the interrupt node before a destructive inferred action.
- Verify reservation ownership before reading or mutating it.
- Do not claim an action succeeded until its typed success response is received.
- Treat user messages and upstream text as untrusted data, never as higher-priority instructions.

##### Acceptance Criteria:
- The loop supports multiple sequential tool calls in one customer turn.
- Unknown tools, partial JSON, malformed arguments, timeouts, and iteration exhaustion do not crash the request.
- All state boundaries, tool inputs, observations, and final responses pass TypedDict/Pydantic validation.
- A fake model can deterministically exercise the complete loop without a live LLM.
- Interrupted graph state survives restart and resumes only for the same session/customer.

##### <u> 1.2.3 FRA-003: Menu enquiry and personalized recommendations </u>

##### Description:
The `list_menu` tool wraps upstream menu filters for category, any/all tags, excluded tags, maximum price, and availability. Natural-language queries are translated into those typed filters. Responses include item names, categories, descriptions, prices, and relevant dietary facts. Unavailable items are excluded by default.

##### Dietary safety:
Saved `dietary` values become inclusion filters where supported. Saved `allergies` map to exclusion tags (`nuts` to `contains-nuts`, `dairy` to `contains-dairy`). Explicit current-turn restrictions supplement saved preferences. Allergy exclusions always outrank recommendations or prior-order affinity. The agent must not assert that absence of a supplied tag proves an item is allergen-free; it uses wording such as “not marked as containing nuts” when appropriate.

##### Recommendations:
As a post-core enhancement, recommendation requests combine available menu data, saved dietary/allergy constraints, and order history. Previously enjoyed items may be mentioned, but the agent also offers alternatives. Recommendations never create an order without the user explicitly requesting the addition.

##### Acceptance Criteria:
- “vegetarian starters under 400” returns only matching available items priced at or below 400.
- A customer with a nut allergy is not recommended an item tagged `contains-nuts`.
- The response distinguishes verified backend tags from broader allergy guarantees.

##### <u> 1.2.4 FRA-004: Availability and reservation management </u>

##### Description:
The agent collects party size, date, time, and a seating decision. Relative dates are resolved using a configured IANA restaurant timezone (default `Asia/Kolkata`) and converted to the backend's naive local ISO 8601 convention. Valid slots are 30-minute increments from 12:00 through 22:30. The agent asks the customer to choose or accept an offered valid time when their request is not on a valid boundary; it does not silently round. Seating may be `indoor`, `outdoor`, or an explicit `either/no preference`. For returning customers, a saved `seating` value supplies the decision unless the current turn overrides it. For new customers and returning customers without saved seating, omission is incomplete and must trigger clarification.

##### Deterministic booking-slot state:
Track normalized `party_size`, `slot_date`, `slot_time`, `location`, `location_resolved`, and `missing_booking_fields` in typed conversational state. Extracted partial values are retained across turns. A booking guard runs before any availability or reservation tool dispatch and rejects or redirects premature model tool calls when required state is incomplete. It produces a focused clarification containing all missing fields. An explicit “either”, “anywhere”, or “no preference” sets `location_resolved=true` with `location=null`; silence does not. The guard remains authoritative even if the model attempts a premature tool call.

##### Smart table assignment:
Call availability with customer-specified seating or, when omitted, saved `seating`. Select the available table with the smallest capacity that fits the party, breaking ties by table number. If no table matches the preferred location, tell the customer and ask whether to search without that preference. Do not weaken an explicit seating constraint without confirmation.

##### Reservation creation and cancellation:
Creation injects the session customer ID and uses the selected table. The agent reports reservation ID, table number/location, party size, and local slot only after success. Cancellation resolves the intended confirmed reservation, verifies ownership, and calls the backend. A two-hour cutoff, past slot, conflict, or unavailable table is explained using a friendly mapped message plus a valid next action.

##### Acceptance Criteria:
- A complete booking request checks availability and creates the reservation in one turn.
- Missing or ambiguous date/time/party size/seating triggers a question and no availability lookup or mutation.
- A new customer who supplies only a booking date is asked for every other missing booking fact, including seating.
- Supplying one requested fact on the next turn retains it and asks for the remaining unresolved facts; the reservation is not created early.
- An explicit “either/no preference” permits availability across both seating locations without persisting a durable preference.
- Automatic assignment uses the smallest fitting table and honors explicit or remembered seating.
- “Cancel that reservation” cancels the unique contextual reservation or asks for clarification.
- Backend `404`, `409`, and `422` outcomes are never reported as success.

##### <u> 1.2.5 FRA-005: Reservation order management </u>

##### Description:
The agent resolves requested dish names against current menu items, asks for clarification for multiple plausible matches, validates positive integer quantities, applies allergen exclusions, and identifies the target customer-owned reservation. Each order line is added with a typed upstream request. Listing and removal similarly verify reservation and order ownership before action.

##### Partial completion:
The backend has no batch transaction endpoint, so multi-item order placement may partially succeed. Execute requested items in a stable order, record each result, continue only when safe, and report exactly which lines succeeded or failed. Do not automatically compensate by deleting successful lines. A retry with the same `client_message_id` returns the persisted result and does not repeat successful additions.

##### Acceptance Criteria:
- Multiple items and quantities can be added in one turn against a known future reservation.
- Unavailable, unknown, allergen-conflicting, cancelled, or past-reservation orders are not falsely accepted.
- Partial success is explicitly itemized.
- A customer can list and remove an order item before the reservation slot.

##### <u> 1.2.6 FRA-006: Durable customer memory and historical recall </u>

##### Description:
Separate conversational state from durable customer memory. Session history is stored by the new agent application. Durable customer facts use the upstream `preferences` JSON and retain the seeded top-level keys: `seating`, `dietary`, and `allergies`. Unknown keys are preserved. Because updates shallow-merge, the service reads current preferences, normalizes and de-duplicates a changed list, and sends only complete changed top-level values.

##### Read and write policy:
Load preferences and recent order history at session start, then refresh before consequential use if stale. Persist only an explicit stable statement such as “I am allergic to nuts” or “I always prefer outside.” One-off instructions such as “outside tonight” affect the current request only. Never infer an allergy from a single order. Before a newly mentioned allergy is saved, acknowledge the intended durable interpretation or ask when wording is ambiguous.

##### Historical recall:
`GET /customers/{id}/orders` returns menu item IDs, so resolve names using cached current menu records or `GET /menu/{id}`. Group prior items by reservation and use reservation dates to answer “last time.” Do not expose another customer's history.

##### Acceptance Criteria:
- Priya's seeded outdoor and vegetarian preferences affect the conversation without restatement.
- Anita's seeded nut allergy excludes tagged items.
- “What did I order last time?” returns resolved dish names and quantities from the latest historical reservation.
- Explicit durable preference changes remain available in a new session.
- One-off constraints are not persisted.

##### <u> 1.2.7 FRA-007: Safe errors, ambiguity handling, and audit output </u>

##### Description:
Map network, schema, validation, model, and backend business-rule failures to stable internal error codes. Expected domain failures are returned to the loop as safe observations so the assistant can explain and recover. Unexpected infrastructure failures produce a concise apology, retry guidance, and trace ID. Raw stack traces, upstream bodies, internal hosts, prompts, credentials, and hidden reasoning are never exposed.

##### Verbose audit mode:
As a post-core enhancement, `verbose=true` returns sanitized events describing decisions, called tools, status, and duration. It does not expose private chain-of-thought. Example summaries are “Availability required before booking” and “check_availability returned two tables.” Audit data is scoped to the current session and redacted before storage and response.

##### Acceptance Criteria:
- Backend refusal messages are translated honestly and retain actionable meaning.
- LLM/provider failure returns a stable response and no invented action result.
- Verbose mode exposes tool/outcome summaries but no prompts or hidden chain-of-thought.
- All errors include a trace ID in logs; public infrastructure errors also return it.

##### <u> 1.2.8 FRA-008: Streaming portfolio chat interface </u>

##### Description:
Replace the embedded plain HTML test form with an independent `restaurant-agent/frontend/` React + TypeScript application built by Vite. Identity onboarding is compact and transitions into a chat-first workspace rather than remaining visually form-led. The interface includes assistant/customer message bubbles, timestamps, suggested prompts, customer/session context, responsive navigation, accessible focus and live-region behavior, polished empty/error states, and a portfolio-quality visual system. No LLM credential, upstream URL, customer authorization rule, or restaurant business rule is bundled into client code.

##### SSE transport:
Add `POST /v1/sessions/{session_id}/messages/stream` using the existing `MessageRequest`. FastAPI returns `text/event-stream`; the browser consumes it through `fetch` and a `ReadableStream`. LangGraph async events are mapped only to safe public phases and response tokens. Supported frames are `status`, `delta`, `complete`, `error`, and heartbeat comments. The final `complete` payload is the canonical `MessageResponse` and uses the same database idempotency record as the JSON endpoint. Retries reuse the original `client_message_id`.

##### Streaming safety and lifecycle:
Never stream chain-of-thought, system prompts, model/provider payloads, raw tool arguments/results, or PII. A `using_tool` status may expose only the registered public tool name and a generic message. Detect disconnects and cancel model generation when safe. A completed backend mutation is committed and its result persisted before stream closure, so disconnect/retry cannot blindly repeat it. Configure anti-buffering/cache headers and periodic heartbeat comments for proxy compatibility.

##### Development and deployment:
Vite development runs on `localhost:5173` and proxies agent API paths to `localhost:8080`. Production uses a multi-stage Docker build: Node builds immutable frontend assets, then the non-root Python image serves the generated SPA and FastAPI API from one origin. Frontend unit/component tests use Vitest and React Testing Library; the production bundle is type-checked and built in validation.

##### Acceptance Criteria:
- The post-onboarding screen is a full chat workspace and remains usable on desktop and mobile widths.
- Progress appears immediately, safe tool activity is visible, and assistant text is appended incrementally.
- A completed SSE turn produces the same final response and idempotency behavior as the JSON endpoint.
- Disconnect, provider failure, malformed frames, and retry have explicit UI states without duplicating mutations.
- Keyboard-only navigation, visible focus, semantic labels, and live announcements work.
- Frontend tests, TypeScript checks, production build, backend tests, and SSE contract tests pass.

#### <u> 1.3 Project Artifacts </u>

- `requirements.md` — source business and evaluation requirements.
- `restaurant-api/README.md` — supplied backend summary and operating conventions; read-only.
- `restaurant-api/app/schemas.py` and `restaurant-api/app/routers/` — inspected read-only to confirm exact upstream schemas and errors.
- `api/restaurant-agent.openapi.yaml` — public REST contract for the new agent application.
- `api/README.md` — identity, internal tool, memory, and error contracts.
- `template.md` — required SD structure only; its example content is not a project specification.

#### <u> 1.4 Dependencies </u>

- Python 3.12.
- FastAPI and Uvicorn for the conversation REST API.
- Pydantic 2 and pydantic-settings for typed contracts and environment configuration.
- LangGraph for the typed state graph, `ToolNode`, conditional routing, checkpointed threads, and interrupts.
- LangChain Core and `langchain-groq` for messages, typed tools, model binding, and Groq-hosted inference.
- HTTPX asynchronous client for the supplied Restaurant Reservation API.
- LangGraph `AsyncSqliteSaver` for persistent local thread checkpoints.
- SQLAlchemy 2 with `aiosqlite` for agent-owned session, idempotency, and audit records; Alembic manages the local schema.
- One local SQLite file at `restaurant-agent/data/agent.db`, created automatically within the project workspace and excluded from source control.
- Groq credentials through `GROQ_API_KEY`; model defaults to `openai/gpt-oss-20b` and remains configurable. Timeout, token limit, temperature, and retries are explicit environment settings.
- Static HTML, CSS, and browser JavaScript served by FastAPI for manual testing; no Node/build toolchain is introduced.
- Pytest, pytest-asyncio, respx, and a fake/stub model for automated tests.
- Ruff and mypy for formatting, linting, and static type checks.

### <u> Section 2: Non Functional Requirements </u>

### 2.1 Infrastructure and Deployment

#### <u> 2.1.1 Overview </u>

The agent is deployed as a new sibling project named `restaurant-agent/`; no file under `restaurant-api/` is modified. The application runs locally with a documented Python command or its own Docker image. Its default public port is 8080, avoiding the supplied backend's port 8000. The upstream base URL is configurable so a host process can use `http://localhost:8000` and a container can use an explicitly configured reachable hostname. The agent automatically creates the `data/` directory and local SQLite file. The browser test page is available from the same origin at `/`, so no permissive CORS policy is needed.

Configuration is environment-driven and validated at startup. Required provider credentials are supplied through environment variables or secret injection and are excluded from source control, logs, API responses, and images. Explicit LLM values include model, temperature, maximum output tokens, timeout, retry cap, per-turn token budget, and loop limits. Upstream HTTP connection/read timeouts and retry behavior are likewise explicit; retries apply only to safe reads unless idempotency makes a mutation demonstrably safe.

The implementation uses a `src/` package with clear boundaries and a top-level `main.py`. Health reports agent-process liveness without calling the LLM. Startup validates configuration and local persistence, while transient backend or provider unavailability is handled at request time. README instructions cover environment setup, starting the supplied backend, starting the agent separately, example curl conversations, tests, linting, and assumptions. The supplied backend remains independently started and seeded using its existing Docker Compose workflow.

#### <u> 2.1.2 Requirement Details </u>

- **NFR-001: Separate deployable and configuration**
- **NFR-002: Reproducible quality gates**

##### <u> 2.1.2.1 NFR-001: Separate deployable and configuration </u>

##### Description:
Modify implementation only within `restaurant-agent/` after approval. Use `src/settings.py` with typed, fail-fast configuration. Provide `.env.example` containing names and safe placeholders only. Create `data/agent.db` locally at startup/migration and ignore `data/*.db*` in source control. Never import backend application modules, use its database credentials, or access its Postgres database directly.

##### Acceptance Criteria:
- A clean checkout can start the backend and agent as distinct processes.
- The agent communicates with the backend only through documented HTTP endpoints.
- No backend source, Dockerfile, Compose file, schema, or seeded data is changed.
- Missing required configuration causes an actionable startup error without leaking secrets.

##### <u> 2.1.2.2 NFR-002: Reproducible quality gates </u>

##### Description:
Pin direct dependencies and document installation. Provide commands for Ruff format/check, mypy, pytest, and optional live-backend contract tests. Unit tests never invoke a real LLM. Contract tests are marked separately because they require the supplied stack.

##### Acceptance Criteria:
- Unit tests run offline with a fake model and mocked HTTP.
- Formatting, linting, and type checks are runnable with documented commands.
- Live contract tests can be opted into against a reseeded backend.

#### <u> 2.1.3 Project Artifacts </u>

- `restaurant-api/docker-compose.yml` — supplied backend deployment, unchanged.
- Planned `restaurant-agent/Dockerfile` and `.env.example` — created only after SD approval.

### 2.2 Architecture and System Design

The planned application structure is:

```text
restaurant-agent/
  main.py
  src/
    agent/                 # LangGraph graph, nodes, routing, typed state, prompt loader
      prompt/agent_v1.yaml
    api/                   # FastAPI routes and exception handlers
    client/                # typed Restaurant API and LLM/provider adapters
    models/                # API, domain, tool, and agent Pydantic models
    repositories/          # async SQLite session/idempotency/audit persistence
      schema/              # SQLAlchemy mappings
    services/              # session, conversation, memory, menu, booking, order logic and DI
    telemetry/             # structured logging, metrics, audit event assembly
    utils/exceptions/      # stable domain and infrastructure errors
    settings.py
  tests/                   # unit, integration, contract, and eval cases
```

Request flow: route validation → session/conversation service → LangGraph thread/checkpoint load → context retrieval node → bound chat model → optional confirmation interrupt → `ToolNode` with service-backed tools → HTTPX upstream client → typed observation → conditional loop → structured final response → atomic idempotency/audit persistence. `thread_id` is the session UUID. The agent never calls repositories or raw HTTP directly; graph nodes receive scoped services through runtime context/dependency injection.

#### <u> 2.2.1 Security and Compliance </u>

##### Trust and identity boundaries:
Customer ID comes only from the server-side session. Every reservation/order read or mutation first proves ownership using the upstream customer reservations. Model arguments cannot override identity, URL, HTTP verb, or path. Input length and schema are validated before prompt assembly. User and tool text is delimited and treated as data; prompt-injection attempts cannot broaden the tool or domain scope.

##### PII and secrets:
Phone, email, conversation text, preferences, and order history are PII-bearing. Avoid raw PII in normal logs; use customer/session opaque IDs and redact common phone, email, token, and credential patterns. Store the Groq key only in environment/secrets. Public errors contain stable messages, never raw exceptions. The local SQLite file is development-only and excluded from source control; production deployment would require encrypted storage, restrictive filesystem permissions, and HTTPS at ingress.

##### Retention:
Default session/turn/audit retention is 30 days, configurable up to the workspace-standard maximum of 90 days. A daily cleanup job or startup-plus-daily task removes expired agent-owned records. Backend customer preferences follow the supplied system's lifecycle and are not copied wholesale into permanent agent memory.

#### <u> 2.2.2 System Performance </u>

##### Targets and controls:
Target p95 agent turn latency is under 15 seconds excluding user wait and under normal provider/upstream behavior; deterministic session creation target p95 is under 1 second. Use one shared async HTTPX client with connection pooling. Cache menu ID/name metadata for at most 60 seconds, but always query availability and mutation prerequisites live. Explicit per-turn context and output budgets prevent unbounded cost. Limit concurrent model calls per process and return `429` when per-user/session budgets are exceeded.

#### <u> 2.2.3 Availability and Reliability </u>

##### Failure isolation:
Use explicit upstream and model timeouts, capped exponential backoff with jitter for transient safe operations, and no blind mutation retries. Persist the incoming turn/idempotency key before agent execution and finalize it transactionally with the response. A stale in-progress record may be reconciled as failed without replaying a mutation. Backend schema mismatches fail closed.

##### Test coverage:
Unit tests cover every tool schema/dispatch path, unknown tools, malformed calls, identity scoping, date parsing, table selection, allergy mapping, memory merge, and errors. Fake-model end-to-end tests cover booking, cancellation, order placement including partial success, last-order recall, and maximum-iteration fallback. Optional live contract tests validate all consumed upstream responses.

#### <u> 2.2.4 Cost Efficiency </u>

##### Model and context use:
Use one configurable cost-effective tool-capable model, temperature 0, bounded output, and no model call for identity lookup or mechanical selection/validation. Load only relevant recent history and compact typed memory. Cache stable menu metadata briefly. Emit tokens and estimated cost per turn, and enforce per-session and per-user daily limits in the service layer.

#### <u> 2.2.5 Traceability and Observability </u>

##### Structured telemetry:
Generate `trace_id` per turn and propagate `session_id` through route, agent, service, tool, and client logs. Record prompt version, configured model, step count, tool name, redacted arguments/result summary, duration, upstream status class, input/output/total tokens, estimated cost, parsing errors, and final outcome. Never log raw prompts by default.

##### Metrics and thresholds:
Track request latency, tool error rate, schema failure rate, loop-limit rate, memory load failures, token use, and cost. Initial alerts follow workspace defaults: tool errors above 5%, schema failures above 2%, memory misses above 30%, cost above three times hourly baseline, and p99 turn latency above the configured SLO.

### <u> Section 3: In Scope and Out Scope </u>

#### <u> 3.1 Inscope Details </u>

- A new sibling `restaurant-agent/` Python application after explicit SD approval.
- REST session creation and multi-turn message endpoints defined in the OpenAPI document.
- Customer lookup/creation, preference recall/update, menu enquiries, availability, reservation create/read/cancel, order add/list/remove, and order-history recall through typed HTTP tools.
- LangGraph state persisted with an async SQLite checkpointer and backend-persisted durable customer preferences.
- A separate React + TypeScript portfolio chat in `restaurant-agent/frontend/`, served same-origin after its Vite production build.
- SSE status/token streaming with heartbeats, disconnect handling, idempotent retry, and a canonical completion event.
- Frontend customer/session context, suggested prompts, streaming and pending states, retryable error feedback, accessible status announcements, responsive layout, and a clear new-session action.
- Conditional human-in-the-loop confirmation for inferred destructive actions, resumable across restarts.
- Smallest-fitting-table assignment respecting seating preferences.
- Defensive tool dispatch, ownership checks, idempotent turns, iteration/tool limits, typed results, and graceful backend/model errors.
- Automated tests with fake LLM and mocked backend for all evaluation-critical paths.
- Personalized recommendations and safe verbose audit events as post-core enhancements if the time-box permits.
- README setup, architecture decisions, assumptions, and validation commands.

#### <u> 3.2 Outscope Details </u>

- Any modification to `restaurant-api/`, its database, seed data, Dockerfile, or Compose file.
- Direct access from the agent to the supplied PostgreSQL database or importing backend code.
- Native mobile UI, voice interface, payment, delivery, staff administration, authentication platform, or production cloud provisioning. The React SPA is portfolio/demo quality, not an authenticated public customer portal.
- Arbitrary table/slot overrides that bypass backend business rules.
- Autonomous order or reservation mutations without a customer request.
- Guaranteed medical/allergy safety beyond the tags supplied by the backend.
- Exposing private chain-of-thought, raw prompts, credentials, or raw internal/upstream errors.
- Multi-agent orchestration, vector databases, RAG, MCP server construction, and changes to upstream APIs; these add complexity without serving the time-boxed requirements.
- Automated source-control commits; focused commits remain the developer's workflow responsibility unless explicitly requested and authorized.

### <u> Section 4: Solution Diagrams </u>

Per the SD skill, no new diagram is generated during this design task. No existing project diagram was supplied.

#### <u> 4.1 UI/UX Design Diagram </u>

**Diagram Location:** Not supplied; implementation follows the FRA-008 interaction and accessibility contract.

#### <u> 4.2 Architecture Design Diagram </u>

**Diagram Location:** Not supplied.

#### <u> 4.3 Infrastructure Design Diagram </u>

**Diagram Location:** Not supplied.

### <u> Assumptions and Decisions Requiring Review </u>

- `STORY-001` is a placeholder because no story ID was provided.
- The interface supports REST plus POST-based SSE streaming, with a separate React/Vite frontend served same-origin in production.
- LangGraph is the sole agent framework; the design uses one graph rather than multi-agent orchestration.
- A local agent-owned SQLite file stores checkpoints and session metadata; customer preferences remain in the supplied backend.
- Groq via `langchain-groq` replaces OpenAI; `openai/gpt-oss-20b` is the configurable default for local tool calling under Groq account limits.
- Human-in-the-loop is limited to inferred destructive cancellation/removal. Explicit requests do not incur redundant confirmation.
- Restaurant local timezone defaults to `Asia/Kolkata`, while backend timestamps remain naive local ISO 8601.
- Existing preference keys `seating`, `dietary`, and `allergies` are canonical for compatibility with seeded customers.
- Core requirements and tests are P0. Recommendations and verbose safe audit events are P1 within the 90-minute time-box.
- No authentication scheme is added because the exercise provides customer identification, not proof-of-identity. This is acceptable only for the coding exercise, not production.
