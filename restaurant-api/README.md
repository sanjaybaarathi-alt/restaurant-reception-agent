# Restaurant Reservation API (provided backend)

This is the **provided** backend for the Restaurant Reception Agent coding exercise. You will build your agent application **on top of this** — do not modify this codebase.

## Quick start

Requirements: Docker and Docker Compose (Docker Desktop on macOS/Windows, or Docker Engine on Linux).

```bash
docker compose up -d --build
```

The first run will:
1. Start a PostgreSQL container.
2. Build and start the FastAPI service.
3. Create tables and seed sample data automatically.

Verify it is running:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Open the interactive API docs at: <http://localhost:8000/docs>

## Reseeding

Data persists across `docker compose down` and `docker compose up`. To wipe everything and start fresh:

```bash
docker compose down -v
docker compose up -d --build
```

To reseed in place without recreating the database:

```bash
docker compose exec api python -m app.seed --reset
```

## API surface

All endpoints are documented at `/docs`. High-level summary:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/tables` | List tables. Filters: `location`, `min_capacity` |
| GET | `/tables/{id}` | Table details |
| GET | `/menu` | List menu. Filters: `category`, `tags_any`, `tags_all`, `exclude_tags`, `max_price`, `available_only` |
| GET | `/menu/{id}` | Menu item details |
| GET | `/availability` | Tables free at a slot. Params: `slot_datetime`, `party_size`, `location` |
| POST | `/customers` | Create a customer (phone or email required) |
| GET | `/customers/lookup` | Find by `phone` or `email` |
| GET | `/customers/{id}` | Customer profile (includes `preferences`) |
| PATCH | `/customers/{id}/preferences` | Shallow-merge update of `preferences` |
| GET | `/customers/{id}/reservations` | Customer's reservations. Filter: `status` |
| GET | `/customers/{id}/orders` | Customer's order history (across all reservations) |
| POST | `/reservations` | Create a reservation |
| GET | `/reservations/{id}` | Reservation details |
| DELETE | `/reservations/{id}` | Cancel a reservation |
| POST | `/reservations/{id}/orders` | Add an item to a reservation |
| GET | `/reservations/{id}/orders` | List items on a reservation |
| DELETE | `/orders/{id}` | Remove an item from a reservation |

## Conventions

- **Time slots** are 30-minute increments from 12:00 to 22:30 inclusive (`12:00, 12:30, 13:00, ..., 22:30`).
- **Datetimes** are naive ISO 8601 — treat them as local restaurant time.
- **Cancellations** are not allowed within 2 hours of the reservation slot.
- **Customer preferences** is an arbitrary JSON object; the schema is yours to design.

## Seeded data

- **8 tables** — mix of indoor and outdoor; capacities 2 / 4 / 6 / 8.
- **12 menu items** — starters, mains, desserts. Tags include `vegetarian`, `vegan`, `contains-nuts`, `contains-dairy`.
- **3 customers**:
  - Priya Sharma — has order history and stored preferences (outdoor seating, vegetarian).
  - Rahul Verma — no preferences yet.
  - Anita Iyer — nut allergy stored in preferences.

## Stopping

```bash
docker compose down       # stops, keeps data
docker compose down -v    # stops, wipes data
```

## Troubleshooting

- **Port 5432 already in use** — another Postgres is running on your host. Stop it, or change the host port in `docker-compose.yml`.
- **Port 8000 already in use** — change the host port mapping for the `api` service in `docker-compose.yml`.
- **`api` container restarting** — check `docker compose logs api`. If the schema is out of sync after a code change, `docker compose down -v && docker compose up -d --build`.
- **Slow first build** — the initial image build downloads ~150 MB of base layers. Subsequent runs are fast.
