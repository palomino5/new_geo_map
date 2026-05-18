import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

FREE_DAILY_LIMIT = 10


class UserPlan(str, enum.Enum):
    free = "free"
    starter = "starter"
    professional = "professional"
    enterprise = "enterprise"


class User(Base):
    __tablename__ = "user"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[UserPlan] = mapped_column(
        SAEnum(UserPlan, name="user_plan", schema="core"),
        default=UserPlan.free,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    daily_queries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    daily_queries_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    def queries_remaining(self) -> int | None:
        """None means unlimited (paid plan)."""
        if self.plan != UserPlan.free:
            return None
        today = date.today()
        if self.daily_queries_reset_date != today:
            return FREE_DAILY_LIMIT
        return max(0, FREE_DAILY_LIMIT - self.daily_queries_used)

    def consume_query(self) -> bool:
        """Returns False if limit exceeded. Resets counter on new day."""
        if self.plan != UserPlan.free:
            return True
        today = date.today()
        if self.daily_queries_reset_date != today:
            self.daily_queries_used = 0
            self.daily_queries_reset_date = today
        if self.daily_queries_used >= FREE_DAILY_LIMIT:
            return False
        self.daily_queries_used += 1
        return True
