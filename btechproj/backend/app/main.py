"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy import text

from .database import Base, engine
from .routers import dashboard, health, incidents, investigations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("incident-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables and run automatic column migrations on startup."""
    logger.info("Creating database tables")
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS p99_latency_ms DOUBLE PRECISION;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS error_rate DOUBLE PRECISION;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS captured_at TIMESTAMP WITH TIME ZONE;"
                )
            )
            conn.commit()
            logger.info("Database schema column migration completed successfully")
    except Exception as exc:
        logger.warning("Auto-migration notice: %s", exc)
    logger.info("Backend started successfully")
    yield
    logger.info("Backend shutting down")


app = FastAPI(
    title="AI DevOps Incident Investigation Backend",
    description=(
        "Backend service for the AI-Powered DevOps "
        "Incident Investigation System"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Robust CORS middleware configuration for React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(health.router, tags=["Health"])
app.include_router(dashboard.router, tags=["Dashboard & Services"])
app.include_router(
    incidents.router, prefix="/incidents", tags=["Incidents"]
)
app.include_router(
    investigations.router,
    prefix="/investigations",
    tags=["Investigations"],
)


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request, exc: Exception
):
    """Catch-all handler — never expose raw stack traces."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
