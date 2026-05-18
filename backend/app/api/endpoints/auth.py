from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.core.database import get_db
from app.models.user import FREE_DAILY_LIMIT, User, UserPlan

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    plan: UserPlan

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Aquest email ja està registrat")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La contrasenya ha de tenir mínim 8 caràcters")

    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email o contrasenya incorrectes")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte desactivat")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


class UsageOut(BaseModel):
    plan: UserPlan
    daily_limit: int | None
    queries_used_today: int
    queries_remaining: int | None


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/me/usage", response_model=UsageOut)
def me_usage(current_user: User = Depends(get_current_user)) -> UsageOut:
    remaining = current_user.queries_remaining()
    return UsageOut(
        plan=current_user.plan,
        daily_limit=FREE_DAILY_LIMIT if current_user.plan == UserPlan.free else None,
        queries_used_today=current_user.daily_queries_used,
        queries_remaining=remaining,
    )
