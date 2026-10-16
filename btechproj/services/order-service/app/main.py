import logging
import os
from typing import List

import httpx
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .fault_injection import router as fault_router
from .models import Order
from .telemetry import configure_telemetry


# --------------------------------------------------
# Database
# --------------------------------------------------

Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logger = logging.getLogger("order-service")

SERVICE_VERSION = os.getenv("ORDER_SERVICE_VERSION", "v1.3.1")
FAULT_MODE = os.getenv("INCIDENT_ORDER_FAULT_MODE", "none")


# --------------------------------------------------
# FastAPI
# --------------------------------------------------

app = FastAPI(
    title="Order Service",
    description="Order microservice for the AI DevOps Incident Investigation System",
    version=SERVICE_VERSION,
)
configure_telemetry(app, engine, "order-service")
app.include_router(fault_router)


# --------------------------------------------------
# Service URLs
# --------------------------------------------------

# USER_SERVICE_URL = "http://user-service:8000"
# PRODUCT_SERVICE_URL = "http://product-service:8000"

USER_SERVICE_URL = os.getenv(
    "USER_SERVICE_URL",
    "http://user-service:8000"
)

PRODUCT_SERVICE_URL = os.getenv(
    "PRODUCT_SERVICE_URL",
    "http://product-service:8000"
)
PRODUCT_STOCK_FIELD = (
    "available_stock" if FAULT_MODE == "product_contract_regression" else "stock"
)


# --------------------------------------------------
# Schemas
# --------------------------------------------------

class OrderCreate(BaseModel):
    user_id: int
    product_id: int
    quantity: int = Field(gt=0)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# --------------------------------------------------
# Health
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "service": "order-service",
        "status": "healthy",
        "version": SERVICE_VERSION,
    }


# --------------------------------------------------
# GET all orders
# --------------------------------------------------

@app.get(
    "/orders",
    response_model=List[OrderResponse]
)
def get_orders(
    db: Session = Depends(get_db)
):

    logger.info("Fetching all orders")

    orders = db.query(Order).all()

    return orders


# --------------------------------------------------
# GET order
# --------------------------------------------------

@app.get(
    "/orders/{order_id}",
    response_model=OrderResponse
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db)
):

    logger.info(
        "Fetching order id=%s",
        order_id
    )

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    return order


# --------------------------------------------------
# CREATE ORDER
# --------------------------------------------------

@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=201
)
async def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db)
):

    logger.info(
        "Creating order user_id=%s product_id=%s quantity=%s",
        order_data.user_id,
        order_data.product_id,
        order_data.quantity
    )

    # ----------------------------------------------
    # 1. Check user service
    # ----------------------------------------------

    async with httpx.AsyncClient(timeout=5.0) as client:

        try:

            user_response = await client.get(
                f"{USER_SERVICE_URL}/users/{order_data.user_id}"
            )

        except httpx.RequestError as exc:

            logger.error(
                "User service unavailable: %s",
                exc
            )

            raise HTTPException(
                status_code=503,
                detail="User service unavailable"
            )

    if user_response.status_code == 404:

        logger.warning(
            "User id=%s does not exist",
            order_data.user_id
        )

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user_response.status_code != 200:

        raise HTTPException(
            status_code=502,
            detail="Unexpected response from user service"
        )

    # ----------------------------------------------
    # 2. Check product service
    # ----------------------------------------------

    async with httpx.AsyncClient(timeout=5.0) as client:

        try:

            product_response = await client.get(
                f"{PRODUCT_SERVICE_URL}/products/{order_data.product_id}"
            )

        except httpx.RequestError as exc:

            logger.error(
                "Product service unavailable: %s",
                exc
            )

            raise HTTPException(
                status_code=503,
                detail="Product service unavailable"
            )

    if product_response.status_code == 404:

        logger.warning(
            "Product id=%s does not exist",
            order_data.product_id
        )

        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    if product_response.status_code != 200:
        logger.error(
            "Unexpected product-service response status=%s",
            product_response.status_code,
        )

        raise HTTPException(
            status_code=502,
            detail="Unexpected response from product service"
        )

    product = product_response.json()

    # ----------------------------------------------
    # 3. Check stock
    # ----------------------------------------------

    try:
        available_stock = product[PRODUCT_STOCK_FIELD]
    except KeyError:
        logger.exception("Failed to process product-service response")
        raise

    if available_stock < order_data.quantity:

        logger.warning(
            "Insufficient stock for product_id=%s",
            order_data.product_id
        )

        raise HTTPException(
            status_code=400,
            detail="Insufficient stock"
        )

    # ----------------------------------------------
    # 4. Create order
    # ----------------------------------------------

    order = Order(
        user_id=order_data.user_id,
        product_id=order_data.product_id,
        quantity=order_data.quantity,
        status="created"
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    logger.info(
        "Order created successfully id=%s",
        order.id
    )

    return order
