from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from .database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        nullable=False
    )

    product_id = Column(
        Integer,
        nullable=False
    )

    quantity = Column(
        Integer,
        nullable=False
    )

    status = Column(
        String(50),
        nullable=False,
        default="created"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )