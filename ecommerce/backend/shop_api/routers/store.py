"""Customer authentication, catalogue, cart, wishlist, checkout, and profile."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from shop_api.deps import get_current_user, get_db
from shop_api.models import CartItem, Category, Order, Product, User, WishlistItem
from shop_api.schemas import (
    CartAddIn,
    CartOut,
    CartUpdateIn,
    CategoryOut,
    CheckoutIn,
    LoginIn,
    OrderOut,
    PasswordIn,
    ProductOut,
    ProductPage,
    ProfileIn,
    RegisterIn,
    TokenOut,
    UserOut,
)
from shop_api.security import create_access_token, hash_password, verify_password
from shop_api.seed import DEMO_EMAIL
from shop_api.services.checkout import CheckoutError, place_order, shipping_for
from shop_api.services.orders import load_order, order_out

logger = logging.getLogger("ecommerce.store")
router = APIRouter()


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        address_line=user.address_line,
        city=user.city,
        postal_code=user.postal_code,
        country=user.country,
    )


def product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        sku=product.sku,
        slug=product.slug,
        name=product.name,
        description=product.description,
        price_cents=product.price_cents,
        stock=product.stock,
        image_file=product.image_file,
        category_slug=product.category.slug,
        category_name=product.category.name,
    )


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(User).filter(User.email == email).one_or_none():
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip())
    db.add(user)
    db.commit()
    logger.info("customer registered user_id=%s", user.id)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.patch("/profile", response_model=UserOut)
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.full_name = body.full_name.strip()
    user.phone = body.phone.strip()
    user.address_line = body.address_line.strip()
    user.city = body.city.strip()
    user.postal_code = body.postal_code.strip()
    user.country = body.country.strip()
    db.commit()
    return user_out(user)


@router.post("/profile/password", status_code=204)
def change_password(body: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="The current password is incorrect")
    if hmac.compare_digest(body.current_password, body.new_password):
        raise HTTPException(status_code=400, detail="Choose a different password")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return Response(status_code=204)


@router.get("/categories", response_model=list[CategoryOut])
def categories(db: Session = Depends(get_db)):
    rows = db.query(Category).order_by(Category.name).all()
    return [
        CategoryOut(
            slug=row.slug,
            name=row.name,
            description=row.description,
            product_count=len(row.products),
        )
        for row in rows
    ]


@router.get("/products", response_model=ProductPage)
def products(
    q: str | None = None,
    category: str | None = None,
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    in_stock: bool | None = None,
    sort: str = Query(default="newest", pattern="^(newest|name|price_asc|price_desc)$"),
    limit: int = Query(default=24, ge=1, le=48),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Product).join(Category)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Product.name).like(like),
                func.lower(Product.description).like(like),
                func.lower(Product.sku).like(like),
            )
        )
    if category:
        query = query.filter(Category.slug == category)
    if min_price is not None:
        query = query.filter(Product.price_cents >= min_price)
    if max_price is not None:
        query = query.filter(Product.price_cents <= max_price)
    if in_stock is True:
        query = query.filter(Product.stock > 0)
    if in_stock is False:
        query = query.filter(Product.stock == 0)
    total = query.count()
    query = query.options(joinedload(Product.category))
    if sort == "name":
        query = query.order_by(Product.name)
    elif sort == "price_asc":
        query = query.order_by(Product.price_cents, Product.id)
    elif sort == "price_desc":
        query = query.order_by(Product.price_cents.desc(), Product.id)
    else:
        query = query.order_by(Product.created_at.desc(), Product.id.desc())
    rows = query.offset(offset).limit(limit).all()
    return ProductPage(items=[product_out(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/products/{slug}", response_model=ProductOut)
def product_detail(slug: str, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.slug == slug)
        .one_or_none()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_out(product)


def _cart_out(db: Session, user: User) -> CartOut:
    items = (
        db.query(CartItem)
        .options(joinedload(CartItem.product))
        .filter(CartItem.user_id == user.id)
        .order_by(CartItem.id)
        .all()
    )
    lines = []
    subtotal = 0
    for item in items:
        line_total = item.product.price_cents * item.quantity
        subtotal += line_total
        lines.append(
            {
                "id": item.id,
                "product_id": item.product_id,
                "slug": item.product.slug,
                "name": item.product.name,
                "image_file": item.product.image_file,
                "unit_price_cents": item.product.price_cents,
                "quantity": item.quantity,
                "line_total_cents": line_total,
                "stock": item.product.stock,
            }
        )
    shipping = shipping_for(subtotal)
    return CartOut(items=lines, subtotal_cents=subtotal, shipping_cents=shipping, total_cents=subtotal + shipping)


@router.get("/cart", response_model=CartOut)
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _cart_out(db, user)


@router.post("/cart/items", response_model=CartOut, status_code=201)
def add_cart_item(body: CartAddIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.get(Product, body.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock < 1:
        raise HTTPException(status_code=409, detail=f"{product.name} is sold out")
    existing = (
        db.query(CartItem)
        .filter(CartItem.user_id == user.id, CartItem.product_id == product.id)
        .one_or_none()
    )
    quantity = body.quantity if existing is None else existing.quantity + body.quantity
    if quantity > 10:
        raise HTTPException(status_code=400, detail="You can add at most 10 of each product")
    if quantity > product.stock:
        raise HTTPException(status_code=409, detail=f"Only {product.stock} left in stock")
    if existing is None:
        db.add(CartItem(user_id=user.id, product_id=product.id, quantity=body.quantity))
    else:
        existing.quantity = quantity
    db.commit()
    return _cart_out(db, user)


@router.patch("/cart/items/{item_id}", response_model=CartOut)
def update_cart_item(
    item_id: int,
    body: CartUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.user_id == user.id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    if body.quantity > item.product.stock:
        raise HTTPException(status_code=409, detail=f"Only {item.product.stock} left in stock")
    item.quantity = body.quantity
    db.commit()
    return _cart_out(db, user)


@router.delete("/cart/items/{item_id}", response_model=CartOut)
def delete_cart_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.user_id == user.id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return _cart_out(db, user)


@router.get("/wishlist", response_model=list[ProductOut])
def wishlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(WishlistItem)
        .options(joinedload(WishlistItem.product).joinedload(Product.category))
        .filter(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.id.desc())
        .all()
    )
    return [product_out(row.product) for row in rows]


@router.post("/wishlist/{product_id}", status_code=204)
def add_wishlist(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    existing = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id)
        .one_or_none()
    )
    if existing is None:
        db.add(WishlistItem(user_id=user.id, product_id=product_id))
        db.commit()
    return Response(status_code=204)


@router.delete("/wishlist/{product_id}", status_code=204)
def delete_wishlist(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id)
        .one_or_none()
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@router.post("/checkout", response_model=OrderOut)
def checkout(
    body: CheckoutIn,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order, created = place_order(db, user, body, idempotency_key.strip())
    except CheckoutError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": exc.message, "order_id": exc.order_id},
        ) from exc
    response.status_code = 201 if created else 200
    loaded = load_order(db, order.id, user.id)
    return order_out(loaded)


@router.get("/orders", response_model=list[OrderOut])
def orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Order)
        .options(joinedload(Order.items), joinedload(Order.tracking_events), joinedload(Order.payments))
        .filter(Order.user_id == user.id)
        .order_by(Order.id.desc())
        .all()
    )
    rows = sorted({row.id: row for row in rows}.values(), key=lambda row: row.id, reverse=True)
    return [order_out(row) for row in rows]


@router.get("/orders/{order_id}", response_model=OrderOut)
def order_detail(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = load_order(db, order_id, user.id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_out(order)


@router.get("/account/demo")
def demo_hint():
    """Public hint for the local sample customer. The operator account is not included."""
    return {"email": DEMO_EMAIL, "note": "The sample password is in the project README."}
