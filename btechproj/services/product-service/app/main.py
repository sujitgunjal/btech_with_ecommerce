import logging
from decimal import Decimal
from math import prod
from typing import List

from fastapi import Depends,FastAPI,HTTPException

from pydantic import BaseModel,Field
from sqlalchemy.orm import Session

from .database import Base,engine,get_db
from .models import Product
from .telemetry import configure_telemetry

Base.metadata.create_all(bind=engine)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logger = logging.getLogger("product-service")

app = FastAPI(title="product service")
configure_telemetry(app, engine, "product-service")


class ProductCreate(BaseModel):
    name: str = Field(min_length = 1,max_length=150)
    description: str | None = None
    price: Decimal = Field(gt=0)
    stock: int = Field(ge=0)

class ProductResponse(BaseModel):
    id:int
    name:str
    description:str|None
    price: Decimal
    stock: int

    class Config:
        from_attributes = True


@app.get("/health")
def health_check():
    return{
        "service":"product-service",
        "status":"healthy"


    }

@app.get("/products",response_model = List[ProductResponse])
def get_products(db:Session=Depends(get_db)):
    logger.info("Fetching all products")
    products = db.query(Product).all()
    logger.info(
        "Retrieved %d products",
        len(products)

    )
    return products



@app.get("/products/{product_id}",response_model=ProductResponse)
def get_product(product_id:int,db: Session = Depends(get_db)):
    logger.info(
        "Fetching product id=%s",product_id
    )

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        logger.warning(
            "Product id=%s not found",
            product_id
        )

        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return product

@app.post("/products",response_model=ProductResponse,status_code = 201)
def create_product(product_data:ProductCreate,db:Session = Depends(get_db)):
    logger.info("Creating product name=%s",product_data.name)
    product = Product(
        name = product_data.name,
        description=product_data.description,
        price = product_data.price,
        stock = product_data.stock
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    logger.info(
        "Product created id=%s",
        product.id
    )

    return product
