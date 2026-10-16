from typing import List

from fastapi import Depends,FastAPI,HTTPException
from pydantic import BaseModel,EmailStr
from sqlalchemy.orm import Session

from .database import Base,engine,get_db
from .models import User
from .telemetry import configure_telemetry

Base.metadata.create_all(bind=engine)

app = FastAPI(title = "User Service")
configure_telemetry(app, engine, "user-service")

# pydantic schemas

class UserCreate(BaseModel):
    name:str
    email: EmailStr

class UserResponse(BaseModel):
    id:int
    name:str
    email:str

    class Config:
        from_attributes = True

@app.get("/health")
def health_check():
    return{
        "service":"user_service",
        "status":"healthy"
    }

@app.get("/users",response_model=List[UserResponse])
def get_users(db:Session = Depends(get_db)):
    users = db.query(User).all()
    return users


@app.get("/users/{user_id}",response_model=UserResponse)
def get_user(user_id:int,db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(status_code = 404,detail="User not found")

    return user

@app.post(
    "/users",
    response_model = UserResponse,
    status_code = 201
)

def create_user(user_data:UserCreate,db:Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code = 409,detail="Email already registered")
    user = User(
        name = user_data.name,
        email = user_data.email

    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user
