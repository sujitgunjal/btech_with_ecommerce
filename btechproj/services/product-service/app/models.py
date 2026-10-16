from sqlalchemy import Column,Integer,Numeric,String
from .database import Base

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer,primary_key = True,index = True)
    name = Column(String(150),nullable = False)
    description = Column(String(500),nullable=True)
    price = Column(Numeric(10,2),nullable=False)
    stock  = Column(Integer,nullable = False,default = 0)
    