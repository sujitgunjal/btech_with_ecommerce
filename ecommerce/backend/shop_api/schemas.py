"""Request and response models for the customer API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=120)


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=72)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=40)
    address_line: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=80)
    postal_code: str = Field(default="", max_length=20)
    country: str = Field(default="", max_length=80)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    phone: str
    address_line: str
    city: str
    postal_code: str
    country: str


class CategoryOut(BaseModel):
    slug: str
    name: str
    description: str
    product_count: int


class ProductOut(BaseModel):
    id: int
    sku: str
    slug: str
    name: str
    description: str
    price_cents: int
    stock: int
    image_file: str
    category_slug: str
    category_name: str


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int


class CartAddIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=10)


class CartUpdateIn(BaseModel):
    quantity: int = Field(ge=1, le=10)


class CartLineOut(BaseModel):
    id: int
    product_id: int
    slug: str
    name: str
    image_file: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    stock: int


class CartOut(BaseModel):
    items: list[CartLineOut]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int


class CardIn(BaseModel):
    cardholder_name: str = Field(min_length=2, max_length=80)
    card_number: str = Field(min_length=12, max_length=23)
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=2024, le=2100)
    cvc: str = Field(pattern=r"^\d{3,4}$")


class CheckoutIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    address_line: str = Field(min_length=4, max_length=200)
    city: str = Field(min_length=2, max_length=80)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(min_length=2, max_length=80)
    card: CardIn


class OrderItemOut(BaseModel):
    sku: str
    name: str
    unit_price_cents: int
    quantity: int


class TrackingOut(BaseModel):
    status: str
    message: str
    created_at: datetime


class PaymentOut(BaseModel):
    status: str
    amount_cents: int
    reference: str
    failure_reason: str
    created_at: datetime


class OrderOut(BaseModel):
    id: int
    order_number: str
    status: str
    payment_status: str
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    full_name: str
    address_line: str
    city: str
    postal_code: str
    country: str
    card_last4: str
    created_at: datetime
    items: list[OrderItemOut]
    tracking: list[TrackingOut]
    payments: list[PaymentOut]


class ExperimentOut(BaseModel):
    id: int
    kind: Literal["fault", "load"]
    scenario_id: str
    target_service: str
    parameters: dict
    expected_root_cause: str
    outcome: str
    detail: str
    started_at: datetime
    ended_at: datetime | None


class OpsLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class ExperimentStartIn(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    target_service: str = Field(min_length=1, max_length=80)
    parameters: dict[str, int] = Field(default_factory=dict)
