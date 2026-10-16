"""Northline shop API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import TimeoutError as PoolTimeout

from shop_api.database import SessionLocal, database_ready, engine, init_db
from shop_api.routers.ops import recover_orphan_experiments, router as ops_router
from shop_api.routers.store import router as store_router
from shop_api.seed import seed
from shop_api.services.load import runner
from shop_platform.faults import controller
from shop_platform.gate import FaultGate
from shop_platform.logging_json import configure_logging
from shop_platform.settings import get_settings
from shop_platform.telemetry import init_telemetry

settings = get_settings()
configure_logging(settings.otel_service_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production" and settings.jwt_secret == "change-me":
        raise RuntimeError("Set JWT_SECRET before running with APP_ENV=production")
    init_db()
    db = SessionLocal()
    try:
        seed(db)
        recover_orphan_experiments()
    finally:
        db.close()
    from shop_api.services.investigation_bridge import publish_missing_incidents

    publish_missing_incidents()
    yield
    controller.clear("stopped")
    runner.stop()


app = FastAPI(
    title="Northline Shop API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(FaultGate)
init_telemetry(
    app,
    engine,
    settings.otel_service_name,
    settings.otel_exporter_otlp_endpoint,
    settings.deployment_environment,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(store_router)
app.include_router(ops_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.otel_service_name}


@app.get("/health/ready")
def ready():
    try:
        database_ready()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready"}


@app.exception_handler(PoolTimeout)
async def pool_exhausted(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={"detail": "The shop is temporarily unable to reach the database"},
    )
