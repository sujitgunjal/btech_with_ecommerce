"""Checkout with reserved stock, idempotency, and payment rollback."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from shop_platform.faults import controller
from shop_platform.telemetry import (
    record_checkout_error,
    record_inventory_conflict,
    record_order_duration,
    record_payment_failure,
    record_payment_timeout,
)

from ..models import CartItem, Order, OrderItem, Payment, Product, TrackingEvent, User, utcnow
from ..schemas import CheckoutIn
from .payments import PaymentFailed, PaymentTimeout, charge, normalize_card

logger = logging.getLogger("ecommerce.checkout")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
FREE_SHIPPING_OVER = 7500
SHIPPING_CENTS = 500


class CheckoutError(Exception):
    def __init__(self, status_code: int, message: str, order_id: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.order_id = order_id


def shipping_for(subtotal: int) -> int:
    if subtotal <= 0 or subtotal >= FREE_SHIPPING_OVER:
        return 0
    return SHIPPING_CENTS


def place_order(db: Session, user: User, body: CheckoutIn, idempotency_key: str) -> tuple[Order, bool]:
    started = datetime.now(timezone.utc)
    if not IDEMPOTENCY_RE.match(idempotency_key or ""):
        raise CheckoutError(400, "Provide an Idempotency-Key of 8 to 80 letters, numbers, or dashes")

    delay = controller.checkout_delay_seconds()
    if delay:
        import time

        time.sleep(delay)

    existing = (
        db.query(Order)
        .filter(Order.user_id == user.id, Order.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    if controller.inventory_conflict_active():
        record_inventory_conflict()
        record_checkout_error()
        logger.error("inventory conflict while reserving stock user_id=%s", user.id)
        raise CheckoutError(409, "Inventory conflict while reserving stock")

    cart_items = (
        db.query(CartItem).filter(CartItem.user_id == user.id).all()
    )
    if not cart_items:
        raise CheckoutError(400, "Your cart is empty")

    card_number = normalize_card(body.card.card_number)
    if len(card_number) < 13 or len(card_number) > 19:
        raise CheckoutError(400, "Enter a card number of 13 to 19 digits")
    _validate_expiry(body.card.expiry_month, body.card.expiry_year)

    reserved: list[dict] = []
    subtotal = 0
    try:
        for item in cart_items:
            product = db.get(Product, item.product_id)
            if product is None:
                raise CheckoutError(409, "A product in your cart is no longer sold")
            result = db.execute(
                update(Product)
                .where(Product.id == product.id, Product.stock >= item.quantity)
                .values(stock=Product.stock - item.quantity)
            )
            if result.rowcount != 1:
                record_inventory_conflict()
                logger.error(
                    "inventory conflict while reserving stock product_id=%s requested=%s",
                    product.id,
                    item.quantity,
                )
                raise CheckoutError(409, f"{product.name} does not have enough stock")
            subtotal += product.price_cents * item.quantity
            reserved.append(
                {
                    "product_id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "unit_price_cents": product.price_cents,
                    "quantity": item.quantity,
                }
            )
        shipping = shipping_for(subtotal)
        order = Order(
            user_id=user.id,
            idempotency_key=idempotency_key,
            order_number="pending",
            status="pending_payment",
            payment_status="pending",
            subtotal_cents=subtotal,
            shipping_cents=shipping,
            total_cents=subtotal + shipping,
            full_name=body.full_name.strip(),
            address_line=body.address_line.strip(),
            city=body.city.strip(),
            postal_code=body.postal_code.strip(),
            country=body.country.strip(),
            card_last4=card_number[-4:],
        )
        db.add(order)
        db.flush()
        order.order_number = f"NL{order.id:06d}"
        for line in reserved:
            db.add(OrderItem(order_id=order.id, **line))
        db.query(CartItem).filter(CartItem.user_id == user.id).delete()
        db.commit()
    except CheckoutError:
        db.rollback()
        record_checkout_error()
        raise
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Order)
            .filter(Order.user_id == user.id, Order.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            return existing, False
        record_checkout_error()
        raise CheckoutError(409, "This checkout was already submitted")
    except OperationalError as exc:
        db.rollback()
        record_checkout_error()
        logger.error("checkout database contention: %s", exc.__class__.__name__)
        raise CheckoutError(503, "Checkout is busy. Try again in a moment") from exc

    db.refresh(order)
    try:
        payment = charge(order.total_cents, card_number, idempotency_key)
    except PaymentTimeout:
        _fail_payment(db, order, reserved, "timeout", "The payment gateway timed out")
        logger.error("payment gateway timeout order_id=%s", order.id)
        raise CheckoutError(504, "The payment gateway timed out", order.id)
    except PaymentFailed as exc:
        _fail_payment(db, order, reserved, "declined" if exc.declined else "failed", exc.reason)
        logger.error("payment gateway failure order_id=%s reason=%s", order.id, exc.reason)
        status = 402 if exc.declined else 502
        raise CheckoutError(status, exc.reason, order.id)

    order.status = "processing"
    order.payment_status = "paid"
    order.updated_at = utcnow()
    db.add(
        Payment(
            order_id=order.id,
            status="approved",
            amount_cents=order.total_cents,
            reference=payment.get("reference", ""),
        )
    )
    db.add(TrackingEvent(order_id=order.id, status="placed", message="Order placed", created_at=utcnow()))
    db.add(
        TrackingEvent(
            order_id=order.id,
            status="paid",
            message="Payment confirmed",
            created_at=utcnow(),
        )
    )
    db.add(
        TrackingEvent(
            order_id=order.id,
            status="processing",
            message="The warehouse is preparing the order",
            created_at=utcnow(),
        )
    )
    db.commit()
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    record_order_duration(elapsed, "paid")
    logger.info(
        "order paid order_number=%s total_cents=%s duration_ms=%.1f",
        order.order_number,
        order.total_cents,
        elapsed * 1000,
    )
    return order, True


def _fail_payment(db: Session, order: Order, reserved: list[dict], status: str, reason: str) -> None:
    for line in reserved:
        product = db.get(Product, line["product_id"])
        if product is not None:
            product.stock += line["quantity"]
        existing = (
            db.query(CartItem)
            .filter(CartItem.user_id == order.user_id, CartItem.product_id == line["product_id"])
            .one_or_none()
        )
        if existing is None:
            db.add(CartItem(user_id=order.user_id, product_id=line["product_id"], quantity=line["quantity"]))
        else:
            existing.quantity += line["quantity"]
    order.status = "payment_failed"
    order.payment_status = status
    order.updated_at = utcnow()
    db.add(
        Payment(
            order_id=order.id,
            status=status,
            amount_cents=order.total_cents,
            failure_reason=reason[:200],
        )
    )
    db.add(
        TrackingEvent(
            order_id=order.id,
            status="payment_failed",
            message=reason[:240],
            created_at=utcnow(),
        )
    )
    db.commit()
    if status == "timeout":
        record_payment_timeout()
    else:
        record_payment_failure()
    record_checkout_error()
    record_order_duration(0.0, status)


def _validate_expiry(month: int, year: int) -> None:
    today = datetime.now(timezone.utc)
    if year < today.year or (year == today.year and month < today.month):
        raise CheckoutError(400, "The card has expired")
