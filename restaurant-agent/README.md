# Restaurant Reception Agent

A separate FastAPI + LangGraph application that provides multi-turn restaurant reception conversations over the supplied Restaurant Reservation API. The supplied `../restaurant-api/` is treated as a read-only HTTP service and is never imported or modified.

## Architecture

- FastAPI exposes identified sessions and conversational turns on port 8080.
- LangGraph implements a typed retrieve → plan → optional confirmation → tools → respond loop.
- Customer-scoped LangChain tools wrap the supplied API and prevent model-controlled identity or URLs.
- A local SQLite database at `data/agent.db` stores LangGraph checkpoints, sessions, and message idempotency records.
- A lightweight same-origin browser client is served at `/` for manual testing.
- The portfolio frontend is a separate React + TypeScript application in `frontend/`; production assets are built by Docker and served same-origin.
- `POST /v1/sessions/{session_id}/messages/stream` emits SSE progress, response deltas, and the canonical idempotent completion.
- Booking tools are deterministically gated until party size, date/time, and seating are resolved; new customers must choose indoor, outdoor, or explicitly either.
- Runtime logs are emitted as privacy-redacted JSON and responses include restrictive browser security headers.
- Durable seating, dietary, and allergy preferences remain in the supplied backend.
- Customer confirmation interrupts are used only for destructive actions inferred without an explicit cancellation/removal request.

## Run locally with Docker

Start the supplied backend without changing it:

```powershell
cd ..\restaurant-api
docker compose up -d --build
```

Configure and start the separate agent:

```powershell
cd ..\restaurant-agent
Copy-Item .env.example .env
# Put your Groq API key in .env
docker compose up -d --build
```

Open `http://localhost:8080` to use the test client. The supplied backend remains at `http://localhost:8000`.

The test client includes customer/session context, example prompts, responsive chat layout, pending indicators,
keyboard submission, and retry feedback. Restaurant decisions remain in the agent rather than browser JavaScript.

For frontend hot reload (Node 24+), keep FastAPI on port 8080 and run:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`; Vite proxies agent API calls to port 8080. Frontend validation uses
`npm test` and `npm run build`. Docker performs both checks in its frontend build stage.

## Example conversation

```powershell
$session = Invoke-RestMethod -Method Post -Uri http://localhost:8080/v1/sessions `
  -ContentType application/json `
  -Body '{"customer":{"phone":"+91-9876543210"}}'

$body = @{client_message_id="demo-1"; message="Book a table for 3 tomorrow at 8 PM"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/v1/sessions/$($session.session_id)/messages" `
  -ContentType application/json -Body $body
```

Use a new `client_message_id` for each new turn. Retrying the same ID and message returns the stored response without repeating mutations.

## Python development

Python 3.12+ is required. The preferred package manager is `uv`:

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```

When running outside Docker, set `RESTAURANT_API_BASE_URL=http://localhost:8000`. SQLite creates
`data/agent.db` during migration; no separate agent database server is required.

Validation commands:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src main.py
uv run pytest --cov=src --cov-report=term-missing
```

## Endpoints

- `GET /health` and `/healthz`: process liveness.
- `GET /`: same-origin browser test client.
- `GET /ready` and `/readyz`: agent database and supplied-backend readiness.
- `POST /v1/sessions`: lookup or create an identified customer and start a session.
- `POST /v1/sessions/{session_id}/messages`: process or resume one idempotent turn.
- `POST /v1/sessions/{session_id}/messages/stream`: stream safe progress and assistant output over SSE.
- Interactive API documentation: `http://localhost:8080/docs`.

The authoritative contract is `../api/restaurant-agent.openapi.yaml`.

## Configuration and security

All provider and service settings are environment-driven. Set `GROQ_API_KEY` and optionally change
`AGENT_MODEL` (default `openai/gpt-oss-20b`). Never commit `.env`. `LANGGRAPH_STRICT_MSGPACK=true`
restricts checkpoint deserialization. Normal logs redact common email, phone, credential, and token
values. The exercise identifies customers but does not authenticate ownership of phone/email;
production deployment requires real authentication, HTTPS, encrypted storage, rate limiting, and a
managed secret store.

SQLite is intentionally used for this local/test build. Run a single agent process because SQLite and
its LangGraph checkpointer are not intended for horizontally scaled production replicas. Before a
public deployment, migrate agent persistence to a managed PostgreSQL-compatible checkpointer and add
authentication, per-customer rate limits, centralized telemetry, and encrypted backups.

## Business behavior and assumptions

- Restaurant-local timezone defaults to `Asia/Kolkata`; upstream datetimes are sent as naive local ISO 8601.
- Invalid slot times are clarified rather than silently rounded.
- Availability results are sorted to choose the smallest fitting table, then lowest table number.
- Existing `seating`, `dietary`, and `allergies` preference keys are retained.
- Allergy behavior is based only on supplied menu tags and is not a medical guarantee.
- Multi-item orders are not transactional because the supplied backend has no batch endpoint; partial successes must be reported exactly.
- A 30-day agent-session retention policy is designed but automated deletion is a production follow-up.
- Personalized recommendations and verbose audit events are secondary to the core booking, cancellation, ordering, and recall flows.
