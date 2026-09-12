"""Application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.metrics import metrics_middleware, render_metrics
from app.routes import health_router, refresh_gauges, router

logging.basicConfig(
    level=settings.log_level,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("safahawa.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("API starting; database target comes from DATABASE_URL")
    yield
    log.info("API shutting down; closing connection pool")
    from app.db import engine

    engine.dispose()


app = FastAPI(
    lifespan=lifespan,
    title="safa Hawa API",
    version="1.0.0",
    description=(
        "Hourly air quality readings for the Kathmandu Valley. "
        "Read-only: the ingest poller is the only writer."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.middleware("http")(metrics_middleware)

app.include_router(router)
app.include_router(health_router)


@app.get("/metrics", include_in_schema=False)
def metrics():
    refresh_gauges()
    return render_metrics()


@app.get("/", include_in_schema=False)
def root():
    return {"service": "safa-hawa-api", "docs": "/docs", "health": "/healthz"}
