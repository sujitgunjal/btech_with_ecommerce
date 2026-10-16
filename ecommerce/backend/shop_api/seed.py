"""Create categories, products, and the two built-in customer accounts."""

from sqlalchemy.orm import Session

from shop_platform.settings import get_settings

from .catalogue_data import CATEGORIES, PRODUCTS
from .models import Category, Product, User
from .security import hash_password

DEMO_EMAIL = "demo@northline.shop"
DEMO_PASSWORD = "DemoPass123!"


def seed(db: Session) -> None:
    if db.query(Category).count() == 0:
        categories = {
            slug: Category(slug=slug, name=name, description=description)
            for slug, name, description in CATEGORIES
        }
        db.add_all(categories.values())
        db.flush()
        for sku, slug, name, category_slug, price, stock, description in PRODUCTS:
            db.add(
                Product(
                    sku=sku,
                    slug=slug,
                    name=name,
                    description=description,
                    price_cents=price,
                    stock=stock,
                    image_file=f"{slug}.svg",
                    category_id=categories[category_slug].id,
                )
            )
        db.commit()

    settings = get_settings()
    _ensure_user(
        db,
        DEMO_EMAIL,
        DEMO_PASSWORD,
        "Demo Customer",
        "12 Harbour Street",
        "Lisbon",
        "1100-100",
        "Portugal",
    )
    _ensure_user(
        db,
        settings.load_test_email,
        settings.load_test_password,
        "Load Test Customer",
        "1 Warehouse Lane",
        "Lisbon",
        "1100-200",
        "Portugal",
    )


def _ensure_user(db, email, password, name, address, city, postal, country) -> None:
    if db.query(User).filter(User.email == email).one_or_none():
        return
    db.add(
        User(
            email=email,
            password_hash=hash_password(password),
            full_name=name,
            phone="",
            address_line=address,
            city=city,
            postal_code=postal,
            country=country,
        )
    )
    db.commit()
