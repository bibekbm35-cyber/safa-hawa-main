# Architecture

## The five sentences

Learn these. If you can say them without notes, you can survive most of the
Q&A, because almost every question is a follow-up to one of them.

1. **A poller fetches hourly air quality for eight Kathmandu Valley locations
   from a public API and writes them to Postgres.**
2. **A read-only FastAPI service serves that data to a React dashboard.**
3. **The poller is the only writer; the API has no write endpoints at all.**
4. **Duplicate readings are impossible because of a unique constraint on
   (station, hour), which is what lets the poller safaely re-fetch overlapping
   windows.**
5. **The system reports its own freshness, so a stopped pipeline looks
   different from clean air.**

---

## Why two services

The poller and the API have nothing in common operationally.

| | API | Poller |
|---|---|---|
| Triggered by | User requests, unpredictable | A clock, every 15 minutes |
| Scales with | Traffic | Nothing — one instance is correct |
| Failure means | Users see errors immediately | Data gets stale, silently |
| Correct response to load | Add replicas | Adding replicas would be a **bug** |

That last row is the whole argument. Running three API pods is normal. Running
three pollers means three processes fetching the same hours and racing to
insert them — which the unique constraint makes safae but pointless. They are
different workloads, so they are different deployments with different scaling
rules.

If they were one service, you would have to choose between scaling something
that must not scale and not scaling something that must.

---

## Why the poller does not use the ORM

The API owns the schema through Alembic. The poller writes with plain psycopg
and knows nothing about migrations.

**What this buys:** a smaller poller image with a shorter dependency list, and
a hard guarantee that the poller can never run a migration by accident.

**What this costs:** a deployment ordering requirement. Migrations must have
completed before the poller starts, or it finds no stations and exits. You have
to solve that explicitly — an init container, a Job, a Helm hook.

This is a real tradeoff, not a free lunch. Be able to argue the other side:
sharing a models package would remove the ordering problem at the cost of
coupling the two services' dependency trees together.

---

## Idempotency

```sql
UNIQUE (station_id, observed_at)
```

```sql
INSERT INTO readings (...) VALUES (...)
ON CONFLICT (station_id, observed_at) DO NOTHING
```

Every poll deliberately requests an **overlapping window** — more hours than
have passed since the last poll. That overlap is what repairs gaps left by a
failed run, and the constraint is what makes the resulting duplicates free.

This is why the poller can be killed mid-run, run twice concurrently, or
restarted in a crash loop without corrupting anything. The guarantee lives in
the database, not in application logic, which means it holds even when the
application is behaving badly.

You can demonstrate it in two commands:

```bash
python -m poller.run --backfill-days 30   # 5,888 rows inserted
python -m poller.run --once               # 0 inserted, 320 already present
```

---

## Liveness versus readiness

**`/healthz` — liveness. Touches nothing external.**

If this fails, Kubernetes restarts the pod. It must therefore only fail when
restarting would actually help — that is, when the process itself is wedged.

If liveness checked the database, a thirty-second Postgres blip would fail the
probe on every API pod simultaneously, and Kubernetes would restart all of
them at once. A degraded system becomes a total outage, caused entirely by the
health check.

**`/readyz` — readiness. Checks Postgres. Returns 503 when it is unreachable.**

If this fails, Kubernetes removes the pod from the Service endpoints but leaves
it running. Traffic stops arriving at a pod that cannot serve it, and the pod
rejoins automatically when the database comes back. Nothing restarts.

The short version: **liveness answers "should I be killed?", readiness answers
"should I get traffic?"** Wiring the database check into the first one is the
most common and most damaging mistake in this area.

---

## Data freshness as a product feature

The most dangerous failure this system has is silent. If the poller stops, the
API keeps serving, the charts keep rendering, and yesterday's readings look
exactly like today's. **A dead pipeline and clean air are indistinguishable
from the outside.**

Three things exist to prevent that:

- `poll_runs` — every run records its outcome, so failure is a query, not a
  guess
- `/api/v1/ingest/status` — exposes the age of the newest reading
- `safahawa_data_age_seconds` — the Prometheus gauge you alert on

And in the interface itself, a banner appears when data goes stale. The
dashboard is not allowed to present old data as if it were current.

If you build one Grafana alert, build this one.

---

## Timezone handling

Everything is stored in UTC and displayed in Nepal Standard Time, which is
UTC+5:45 — an offset that will break any code assuming whole-hour timezones.

Daily rollups use `date_trunc('day', observed_at AT TIME ZONE 'Asia/Kathmandu')`
so that a "day" means a Nepali calendar day, not a UTC one. Grouping by UTC day
would split the evening traffic peak across two rows and make the worst hours
of the day disappear into an average.

---

## Why daily AQI is not an average of hourly AQI

This one is worth understanding properly, because it sounds like a nitpick and
is not.

AQI is a **piecewise-linear transform** of pollutant concentration — different
slope in each band. For any non-linear transform, the mean of the transformed
values is not the transform of the mean.

So `AVG(us_aqi)` and `aqi(AVG(pm2_5))` give different numbers, and they can
disagree by enough to move a day across a band boundary — which changes the
public health advice attached to it.

The EPA computes a daily AQI from the daily **mean concentration**. So the
summary endpoint aggregates PM2.5 in SQL and converts to AQI once, in Python,
afterwards.

The original implementation of this endpoint got it wrong. A test caught it.

---

## Request path

```
Browser
  │  GET /api/v1/stations/kalanki/readings?hours=24
  ▼
Ingress / reverse proxy          ── strips nothing, routes /api to the API
  ▼
FastAPI                          ── metrics middleware starts a timer
  │
  ├─ dependency: get_session()   ── one session per request, always closed
  ├─ lookup station by slug      ── 404 if unknown, never an empty list
  ├─ indexed range scan          ── ix_readings_station_observed
  ├─ derive AQI where upstream   ── aqi_from_pm25 fills nulls
  │  omitted it
  ▼
JSON                             ── metrics middleware records latency
                                    under the ROUTE TEMPLATE, not the raw path
```

That last line matters. Labelling metrics with the raw path would create a new
Prometheus time series per station, and per `hours` value — the cardinality
explosion that takes monitoring systems down. The middleware uses
`/api/v1/stations/{slug}/readings`. There is a test that enforces it.

---

## What this system does not have

Know your own boundaries. Saying these out loud is a strength.

- **No authentication.** The data is public and read-only. Adding auth would be
  ceremony without a threat model.
- **No cache.** The daily summary is the expensive query and the obvious
  candidate, but at eight stations and hourly data the whole dataset fits in
  Postgres' buffer cache anyway. Adding Redis here would be resume-driven
  development.
- **No message queue.** One producer, hourly, eight rows a tick. A queue would
  add a failure mode and solve nothing.
- **No service mesh.** Two services that talk to a database and not to each
  other. There is no service-to-service traffic to secure.

Each of those is a real answer to "why didn't you use X?" — and a better one
than having used X.
