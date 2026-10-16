import os

from sqlalchemy import create_engine, true

from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:1234@localhost:5432/devops_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping = True
)

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush = False,
    bind = engine

)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


