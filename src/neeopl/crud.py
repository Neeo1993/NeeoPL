from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Expense, ExpenseTemplate, FactAddition, Income, Period, Saving


def list_periods(db: Session) -> list[Period]:
    return (
        db.query(Period)
        .order_by(Period.year.asc(), Period.month.asc())
        .all()
    )


def get_period(db: Session, period_id: int) -> Period | None:
    return db.get(Period, period_id)


def create_period(db: Session, month: int, year: int, note: str = "") -> Period:
    p = Period(month=month, year=year, note=note)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def delete_period(db: Session, period_id: int) -> None:
    p = db.get(Period, period_id)
    if p:
        db.delete(p)
        db.commit()


def add_income(db: Session, period_id: int, title: str, amount: float) -> Income:
    inc = Income(period_id=period_id, title=title, amount=amount)
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


def update_income(db: Session, income_id: int, title: str, amount: float) -> Income | None:
    inc = db.get(Income, income_id)
    if inc:
        inc.title = title
        inc.amount = amount
        db.commit()
        db.refresh(inc)
    return inc


def delete_income(db: Session, income_id: int) -> None:
    inc = db.get(Income, income_id)
    if inc:
        db.delete(inc)
        db.commit()


def add_saving(db: Session, period_id: int, title: str, amount: float) -> Saving:
    sv = Saving(period_id=period_id, title=title, amount=amount)
    db.add(sv)
    db.commit()
    db.refresh(sv)
    return sv


def update_saving(db: Session, saving_id: int, title: str, amount: float) -> Saving | None:
    sv = db.get(Saving, saving_id)
    if sv:
        sv.title = title
        sv.amount = amount
        db.commit()
        db.refresh(sv)
    return sv


def delete_saving(db: Session, saving_id: int) -> None:
    sv = db.get(Saving, saving_id)
    if sv:
        db.delete(sv)
        db.commit()


def add_expense(
    db: Session, period_id: int, title: str, plan: float, fact: float
) -> Expense:
    exp = Expense(period_id=period_id, title=title, plan=plan, fact=fact)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def delete_expense(db: Session, expense_id: int) -> None:
    exp = db.get(Expense, expense_id)
    if exp:
        db.delete(exp)
        db.commit()


def update_expense(
    db: Session, expense_id: int, title: str, plan: float, fact: float
) -> Expense | None:
    exp = db.get(Expense, expense_id)
    if exp:
        exp.title = title
        exp.plan = plan
        exp.fact = fact
        db.commit()
        db.refresh(exp)
    return exp


def toggle_expense_done(db: Session, expense_id: int) -> Expense | None:
    exp = db.get(Expense, expense_id)
    if exp:
        exp.done = not exp.done
        db.commit()
        db.refresh(exp)
    return exp


def add_fact_with_history(db: Session, expense_id: int, amount: float) -> Expense | None:
    exp = db.get(Expense, expense_id)
    if exp and amount > 0:
        exp.fact = round(exp.fact + amount, 2)
        db.add(FactAddition(expense_id=expense_id, amount=amount))
        db.commit()
        db.refresh(exp)
    return exp


def list_fact_additions(db: Session, expense_id: int) -> list[FactAddition]:
    return (
        db.query(FactAddition)
        .filter(FactAddition.expense_id == expense_id)
        .order_by(FactAddition.created_at.desc())
        .all()
    )


PALETTE = [
    "#6366f1", "#f43f5e", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6",
    "#ec4899", "#14b8a6", "#ef4444", "#0ea5e9", "#84cc16", "#a855f7",
    "#f97316", "#06b6d4", "#d946ef", "#65a30d", "#e11d48", "#7c3aed",
    "#0891b2", "#ca8a04", "#9333ea", "#db2777", "#16a34a", "#2563eb",
]


def _next_color(used: set[str]) -> str:
    import hashlib
    for c in PALETTE:
        if c not in used:
            return c
    raw = hashlib.md5(str(len(used)).encode()).hexdigest()[:6]
    return f"#{raw}"


def list_expense_templates(db: Session) -> list[ExpenseTemplate]:
    return db.query(ExpenseTemplate).order_by(ExpenseTemplate.title).all()


def get_or_create_expense_template(db: Session, title: str, plan: float = 0.0) -> ExpenseTemplate:
    tpl = db.scalar(select(ExpenseTemplate).where(ExpenseTemplate.title == title))
    if tpl:
        return tpl
    used = {t.color for t in db.query(ExpenseTemplate).all()}
    color = _next_color(used)
    tpl = ExpenseTemplate(title=title, plan=plan, color=color)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


def get_template_color(db: Session, title: str) -> str:
    tpl = db.scalar(select(ExpenseTemplate).where(ExpenseTemplate.title == title))
    if tpl:
        return tpl.color
    used = {t.color for t in db.query(ExpenseTemplate).all()}
    return _next_color(used)