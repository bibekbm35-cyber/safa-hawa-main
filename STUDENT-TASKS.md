# Your capstone

The application in this repository works. It has tests, it has migrations, it
has a real data source. What it does not have is any way to build, ship, or run
it anywhere except your laptop.

**That absence is the assignment.**

There is no Dockerfile here. No compose file. No CI workflow. No Kubernetes
manifests. Nothing in `.github/`. You are going to write all of it.

Read that as the job description, because it is one. Platform engineers are
rarely handed a greenfield repo. They are handed something that runs on one
person's machine and asked to make it run everywhere, reliably, for everyone.

---

## Before you write a single line

Get it running locally first. Follow the README. Do not start on Docker until
you have seen the dashboard in your browser with real data in it.

You cannot containerise a thing you have not run.

---

## Phase 1 — Containers

**1.1** Write a Dockerfile for the API.

Start with whatever works. Then make it good:

- Multi-stage, so build tools do not ship in the final image.
- A non-root user. The container must not run as UID 0.
- Layer ordering that lets a code change reuse the dependency layer.
- A `.dockerignore` that keeps `.git`, `__pycache__` and `node_modules` out of
  the build context.

Record the image size after your first attempt and after your last one. That
number is a slide.

**1.2** Write a Dockerfile for the poller.

It is a different image with different dependencies. Resist the urge to reuse
the API image with a different command — think about why, and be ready to say
which choice you made and what it cost.

**1.3** Write a Dockerfile for the frontend.

Two stages: Node builds the static files, then something small serves them. The
runtime stage must not contain Node.

You also have to solve the runtime-config problem described in the README:
`config.js` needs to be rewritten from an environment variable when the
container starts, not when the image is built. An entrypoint script.

**1.4** Scan all three images with Trivy. Fix what you can. For what you cannot
fix, write down why — "this CVE is in a base image dependency we do not call"
is a legitimate answer if you can show it is true. "I ignored it" is not.

**1.5** Write a `docker-compose.yml` that brings up Postgres, the API, the
poller and the web tier together.

Things you have to get right:

- The API must not start before Postgres is accepting connections. A
  `depends_on` alone does not do this. Use a healthcheck condition.
- Migrations must run before the poller starts, or the poller will find no
  stations and exit. Decide where migrations run — think about whether it
  belongs in the API's startup, a separate one-shot service, or something else.
- Postgres data must survive `docker compose down`. Then verify it actually
  does, by doing it.
- No credentials hardcoded in the compose file.

**Checkpoint:** `docker compose up` from a clean clone gives a working
dashboard with data in it. If a judge does this on your laptop and it fails,
nothing else you built matters.

---

## Phase 2 — CI

**2.1** A GitHub Actions workflow that runs on every push and pull request:

- Lint (`ruff` for Python, `eslint` for the web tier)
- Poller tests — these need nothing, so this job should be fast
- API tests — these need a Postgres **service container**
- Frontend build

Run the jobs in parallel where they do not depend on each other. Notice how
much faster that is and be able to say the number.

**2.2** Build and push all three images to a registry, tagged with the commit
SHA. Not `latest`. Be ready to explain why `latest` is a problem in a cluster.

**2.3** Add Trivy to the pipeline. Decide whether a HIGH finding should fail
the build or only warn, and defend your choice.

**2.4** Cache dependencies. Record the before and after pipeline duration.

**Optional but strong:** use OIDC instead of a long-lived registry token. If
you do this, you will be able to answer a question most candidates cannot.

---

## Phase 3 — Kubernetes

**3.1** Manifests for all four workloads. Postgres can be a StatefulSet with a
PVC, or you can use an operator — your call, but know why you chose it.

**3.2** Probes. `/healthz` for liveness, `/readyz` for readiness. Read the
comments on those two handlers before you write the YAML. Getting these
backwards is the single most common mistake in this phase, and it turns a
database blip into a full outage.

**3.3** Resource requests and limits on every container. Do not guess — run the
thing, look at what it actually uses, then set them. Be ready to explain what
happens when a pod exceeds its memory limit versus its CPU limit. They are not
the same.

**3.4** Secrets. The database password must not be in a ConfigMap and must not
be in your Git history. If you commit it by accident, rotating it is part of
the fix, not an optional extra.

**3.5** Solve the migration ordering problem. An init container, a Job, a Helm
hook — pick one, implement it, and be able to say what happens if two API pods
start at the same time and both try to migrate.

**3.6** Decide how the poller runs: CronJob or Deployment. Implement one.
Write down the argument for the other. A judge will ask, and "I picked the one
in the tutorial" is a bad answer where "I picked CronJob because a wedged
long-running poller looks healthy to Kubernetes but a failed Job is visible" is
a good one.

**3.7** Ingress so the dashboard is reachable, with the API routed under
`/api`.

**3.8** A NetworkPolicy that stops the web tier from talking to Postgres
directly. It has no reason to.

**Checkpoint:** deploy to a clean minikube or kind cluster from nothing, in
under ten minutes, while narrating what you are doing.

---

## Phase 4 — Prove it works

This is the part that separates a project from a demo, and it is where most of
your presentation marks are.

**4.1 Break the database.** Delete the Postgres pod. Watch what happens to
`/readyz`. Show the API pods leaving the Service endpoints instead of returning
errors. Show it recovering by itself.

**4.2 Break the upstream.** Point `UPSTREAM_URL` at something that does not
exist. Show the poller retrying with backoff, show the failure landing in
`poll_runs`, show the staleness banner appearing in the dashboard. **This is
your best demo.** The application does not lie about being broken, and you can
prove it in ninety seconds.

**4.3 Kill the poller mid-run.** Show that nothing is corrupted and the next
run repairs the gap. Explain the unique constraint that makes this safae.

**4.4 Roll out a bad image.** Show the readiness probe stopping the rollout
before it takes down the running version.

**4.5** Scrape `/metrics` with Prometheus and put `safahawa_data_age_seconds` on
a Grafana panel with an alert on it. That single metric is the difference
between "the pipeline is down" and "nobody noticed for three days."

---

## Phase 5 — The gaps

Three things in this codebase are deliberately unfinished. Fix them, with
tests, so that part of what you present is yours.

**5.1** There is no endpoint that returns the valley's worst station right now.
The frontend computes it client-side by sorting `/api/v1/latest`, which means
every browser downloads all eight stations to answer a one-line question. Add
`GET /api/v1/worst` and use it.

**5.2** `station_readings` has no upper bound on how much data one request can
return. `hours=720` at eight stations is a lot of JSON. Add pagination, or a
sensible cap with a documented reason.

**5.3** The poller has no metrics of its own. It writes to `poll_runs`, but
nothing exposes that to Prometheus. Add an exporter — either a tiny HTTP
endpoint on the poller, or a Pushgateway, and know the tradeoff between them.

---

## What you will be asked

Write your answers down before the presentation. Say them out loud once. Not to
memorise a script — so that the first time you say the sentence is not in front
of judges.

1. Draw the architecture on a whiteboard from memory.
2. Why are there two Python services instead of one?
3. What happens if the poller runs twice at the same time?
4. Why is `/healthz` different from `/readyz`?
5. Your image is *N* MB. What is in it, and what did you remove?
6. Where does the database password live, and who can read it?
7. The dashboard shows AQI 40. How do I know that is current and not from
   Tuesday?
8. What breaks first if this gets a thousand times more traffic?
9. What did you not build, and why?

Question 9 is not a trap. Knowing the boundary of your own work is a senior
trait, and saying "I did not build a service mesh because nothing here needs
mutual TLS between two services" is a better answer than pretending you did.

---

## One thing to say up front

Open your presentation with this, in your own words:

> The application code was provided to me. My work is everything from the
> Dockerfile onward — containers, pipeline, cluster, observability — plus three
> features I added to the API.

Say it plainly and move on. It is the honest framing, it is the actual job
description for a platform engineer, and judges respect it far more than they
would respect finding out later. Then spend your time on the part that is
yours, which is most of the interesting part anyway.
