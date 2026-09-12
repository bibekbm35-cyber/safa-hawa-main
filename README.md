# safaa Hawa

Hourly air quality for the Kathmandu Valley. Eight monitoring points, one
reading per hour each, going back as far as you choose to backfill.

The valley is a bowl. In winter a temperature inversion puts a lid on it, and
PM2.5 from traffic and brick kilns has nowhere to go — which is why the numbers
in January look nothing like the numbers in July. This application records that,
hour by hour, so you can look at a day, a week, or a season and see the shape of
it.

---

## What is here

```
safa-hawa/
├── api/          FastAPI service. Read-only. Owns the database schema.
├── poller/       Standalone process. Fetches from upstream and writes rows.
├── web/          React dashboard (Vite, plain JavaScript).
├── tools/        Offline stand-in for the upstream API.
└── scripts/      Local development helpers.
```

Three tiers, four processes: **web → api → postgres**, with **poller → postgres**
running alongside on its own schedule.

```
                    ┌──────────────┐
   Open-Meteo ─────▶│    poller    │──── writes ────┐
   (hourly feed)    └──────────────┘                │
                                                    ▼
   ┌─────────┐      ┌──────────────┐          ┌──────────┐
   │   web   │─────▶│     api      │── reads ─│ postgres │
   │ (React) │      │  (FastAPI)   │          └──────────┘
   └─────────┘      └──────────────┘
```

The poller is the only writer. The API has no write endpoints at all.

---

## Running it locally

You need Python 3.12, Node 20+, and a PostgreSQL 16 you can connect to.

**Getting that Postgres running is your first task, and it is not solved for
you.** See [STUDENT-TASKS.md](STUDENT-TASKS.md).

Once you have one:

```bash
cp .env.example .env          # adjust DATABASE_URL to match your Postgres
export $(grep -v '^#' .env | xargs)

# install dependencies
pip install -r api/requirements-dev.txt
pip install -r poller/requirements-dev.txt
(cd web && npm install)

# create the schema and load 30 days of history
./scripts/seed.sh

# run everything
./scripts/dev.sh
```

Then open <http://localhost:5173>.

### Running with no internet

The upstream is a free public API. On presentation day, do not bet on it.

```bash
python tools/fake_upstream.py --port 8555
export UPSTREAM_URL=http://localhost:8555/v1/air-quality
```

Everything works identically. The generated data has realistic morning and
evening traffic peaks and a winter inversion, so the charts still look like
Kathmandu.

To watch the poller's retry logic work, start it with induced failures:

```bash
python tools/fake_upstream.py --port 8555 --failure-rate 0.5
```

---

## The poller

Three modes, and **which one you deploy is a decision you have to make and
defend**:

```bash
python -m poller.run --once              # one poll, then exit 0 or 1
python -m poller.run                     # poll forever on an internal timer
python -m poller.run --backfill-days 30  # load history, then exit
```

`--once` is the shape a Kubernetes CronJob wants: the scheduler owns the
timing, and a failure shows up as a failed Job. The loop mode is the shape a
Deployment wants: one long-lived pod, no per-run startup cost, but you own the
scheduling and a wedged process still looks alive.

Every run writes a row to `poll_runs`, which is what `/api/v1/ingest/status`
and the dashboard's pipeline panel read.

---

## The API

Interactive docs at <http://localhost:8000/docs> once it is running.

| Endpoint | What it gives you |
|---|---|
| `GET /api/v1/stations` | The eight monitoring points |
| `GET /api/v1/latest` | Newest reading at every station |
| `GET /api/v1/stations/{slug}/readings?hours=24` | Hourly series |
| `GET /api/v1/stations/{slug}/summary?days=14` | Daily rollup |
| `GET /api/v1/ingest/status` | Is the pipeline alive, how stale is the data |
| `GET /healthz` | Liveness — touches nothing external |
| `GET /readyz` | Readiness — 503 if Postgres is unreachable |
| `GET /metrics` | Prometheus text format |

`/healthz` and `/readyz` are different on purpose, and the difference matters
when you write your probes. There is a comment in `api/app/routes.py`
explaining why; read it before you wire them up.

---

## Tests

```bash
cd api    && python -m pytest        # needs a Postgres
cd poller && python -m pytest        # needs nothing
```

The split is deliberate. The poller's risky behaviour — parsing upstream
payloads, deciding what to retry — is all testable in memory, so those tests
run in under a second with no dependencies. The API's queries use Postgres
features that SQLite does not implement the same way, so testing them against
SQLite would give you a green suite that proves nothing.

This has a consequence for your CI: the API job needs a database service, the
poller job does not.

---

## Database

Schema lives in `api/alembic/versions/`. Two migrations: the tables, and the
station seed data.

```bash
cd api
python -m alembic upgrade head     # apply
python -m alembic downgrade -1     # roll back one
python -m alembic history          # what exists
```

The API owns the schema. The poller writes with plain SQL and knows nothing
about migrations — so **migrations must have run before the poller starts.**
That ordering is a real problem you will have to solve when you deploy this.

---

## Configuration

Everything that differs between your laptop, CI, and a cluster is an
environment variable. There are no hardcoded hostnames or credentials
anywhere. See `.env.example` for the full list.

The frontend is the interesting case. `web/public/config.js` is served as a
plain file rather than bundled, so its contents can be rewritten when the
container starts. That is what lets you build the image once and run the same
image in two environments. Vite's `import.meta.env` cannot do this — it bakes
values in at build time, which would mean a separate image per environment.

---

## Data source

Open-Meteo's air quality reanalysis, which is free and needs no API key.
Readings are stored in UTC and displayed in Nepal Standard Time (UTC+5:45).

The feed returns forecast hours mixed into the same arrays as observations.
The poller drops anything in the future — storing a forecast as an observation
would make the dashboard present a prediction as a measurement, and nothing
downstream could tell the difference.
