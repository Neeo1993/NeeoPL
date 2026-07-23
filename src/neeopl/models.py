from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incomes: Mapped[list["Income"]] = relationship(
        "Income", back_populates="period", cascade="all, delete-orphan"
    )
    expenses: Mapped[list["Expense"]] = relationship(
        "Expense", back_populates="period", cascade="all, delete-orphan"
    )
    savings: Mapped[list["Saving"]] = relationship(
        "Saving", back_populates="period", cascade="all, delete-orphan"
    )

    @property
    def total_income(self) -> float:
        return round(sum(i.amount for i in self.incomes), 2)

    @property
    def total_plan(self) -> float:
        return round(sum(e.plan for e in self.expenses), 2)

    @property
    def total_fact(self) -> float:
        return round(sum(e.fact for e in self.expenses), 2)

    @property
    def total_savings(self) -> float:
        return round(sum(s.amount for s in self.savings), 2)

    @property
    def delta_expenses(self) -> float:
        return round(self.total_fact - self.total_plan, 2)

    @property
    def delta_income_plan(self) -> float:
        return round(self.total_income - self.total_plan - self.total_savings, 2)

    @property
    def delta_income_fact(self) -> float:
        return round(self.total_income - self.total_fact - self.total_savings, 2)

    @property
    def title(self) -> str:
        months = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
        ]
        return f"{months[self.month - 1]} {self.year}"


class Income(Base):
    __tablename__ = "incomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    period: Mapped["Period"] = relationship("Period", back_populates="incomes")


class Saving(Base):
    __tablename__ = "savings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Накопления")
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    period: Mapped["Period"] = relationship("Period", back_populates="savings")


class ExpenseTemplate(Base):
    __tablename__ = "expense_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    plan: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fact: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    done: Mapped[bool] = mapped_column(default=False)

    period: Mapped["Period"] = relationship("Period", back_populates="expenses")
    additions: Mapped[list["FactAddition"]] = relationship(
        "FactAddition", back_populates="expense", cascade="all, delete-orphan",
        order_by="FactAddition.created_at.desc()"
    )

    @property
    def delta(self) -> float:
        return round(self.fact - self.plan, 2)


class FactAddition(Base):
    __tablename__ = "fact_additions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    expense: Mapped["Expense"] = relationship("Expense", back_populates="additions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)