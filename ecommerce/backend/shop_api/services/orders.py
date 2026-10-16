"""Order serialization and the development-only fulfillment clock."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from shop_platform.settings import get_settings

from ..models import Order, TrackingEvent, utcnow
from ..schemas import OrderOut


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def advance_tracking(db: Session, order: Order) -> None:
    """Move a paid order along a short fulfillment timeline in development."""
    if get_settings().app_env != "development" or order.payment_status != "paid":
        return
    age = (datetime.now(timezone.utc) - as_utc(order.created_at)).total_seconds()
    existing = {event.status for event in order.tracking_events}
    steps: list[tuple[str, str, str]] = []
    if age >= 45 and "shipped" not in existing:
        steps.append(("shipped", "shipped", "The order has been handed to the carrier"))
    if age >= 90 and "out_for_delivery" not in existing:
        steps.append(("shipped", "out_for_delivery", "The parcel is out for delivery"))
    if age >= 120 and "delivered" not in existing:
        steps.append(("delivered", "delivered", "Delivered to the shipping address"))
    if not steps:
        return
    for order_status, event_status, message in steps:
        order.status = order_status
        db.add(
            TrackingEvent(
                order_id=order.id,
                status=event_status,
                message=message,
                created_at=utcnow(),
            )
        )
    order.updated_at = utcnow()
    db.commit()
    db.refresh(order)


def load_order(db: Session, order_id: int, user_id: int) -> Order | None:
    order = (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.tracking_events),
            joinedload(Order.payments),
        )
        .filter(Order.id == order_id, Order.user_id == user_id)
        .first()
    )
    if order is not None:
        advance_tracking(db, order)
    return order


def order_out(order: Order) -> OrderOut:
    tracking = sorted(order.tracking_events, key=lambda event: (as_utc(event.created_at), event.id))
    payments = sorted(order.payments, key=lambda payment: (as_utc(payment.created_at), payment.id))
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        subtotal_cents=order.subtotal_cents,
        shipping_cents=order.shipping_cents,
        total_cents=order.total_cents,
        full_name=order.full_name,
        address_line=order.address_line,
        city=order.city,
        postal_code=order.postal_code,
        country=order.country,
        card_last4=order.card_last4,
        created_at=as_utc(order.created_at),
        items=[
            {
                "sku": item.sku,
                "name": item.name,
                "unit_price_cents": item.unit_price_cents,
                "quantity": item.quantity,
            }
            for item in order.items
        ],
        tracking=[
            {"status": event.status, "message": event.message, "created_at": as_utc(event.created_at)}
            for event in tracking
        ],
        payments=[
            {
                "status": payment.status,
                "amount_cents": payment.amount_cents,
                "reference": payment.reference,
                "failure_reason": payment.failure_reason,
                "created_at": as_utc(payment.created_at),
            }
            for payment in payments
        ],
    )
