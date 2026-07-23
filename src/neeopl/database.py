import json
import shutil
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"
DEFAULT_DB_PATH = DATA_DIR / "neeopl.db"

PALETTE = [
    "#6366f1", "#f43f5e", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6",
    "#ec4899", "#14b8a6", "#ef4444", "#0ea5e9", "#84cc16", "#a855f7",
    "#f97316", "#06b6d4", "#d946ef", "#65a30d", "#e11d48", "#7c3aed",
    "#0891b2", "#ca8a04", "#9333ea", "#db2777", "#16a34a", "#2563eb",
]


def _next_palette_color(used: set[str]) -> str:
    for c in PALETTE:
        if c not in used:
            return c
    import hashlib
    raw = hashlib.md5(str(len(used)).encode()).hexdigest()[:6]
    return f"#{raw}"


CURRENCIES = {
    "RUB": {"symbol": "₽", "locale": "ru-RU"},
    "USD": {"symbol": "$", "locale": "en-US"},
    "EUR": {"symbol": "€", "locale": "de-DE"},
    "KZT": {"symbol": "₸", "locale": "ru-RU"},
    "TRY": {"symbol": "₺", "locale": "tr-TR"},
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_currency() -> str:
    return load_config().get("currency", "RUB")


def get_currency_symbol() -> str:
    return CURRENCIES.get(get_currency(), CURRENCIES["RUB"])["symbol"]


def set_currency(code: str) -> None:
    if code not in CURRENCIES:
        return
    cfg = load_config()
    cfg["currency"] = code
    save_config(cfg)


def get_db_path() -> Path:
    cfg = load_config()
    p = cfg.get("db_path")
    if p:
        return Path(p).expanduser()
    return DEFAULT_DB_PATH


def set_db_path(new_path: Path, move_data: bool = True) -> Path:
    new_path = Path(new_path).expanduser()
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path = get_db_path()
    if move_data and old_path.exists() and old_path.resolve() != new_path.resolve():
        shutil.copy2(old_path, new_path)
    save_config({"db_path": str(new_path)})
    return new_path


DB_PATH = get_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models

    models.Base.metadata.create_all(bind=engine)
    _migrate_savings_to_records()
    _migrate_template_colors()
    _migrate_expense_done()


def _migrate_expense_done() -> None:
    insp = inspect(engine)
    if "expenses" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("expenses")}
    if "done" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE expenses ADD COLUMN done BOOLEAN NOT NULL DEFAULT 0"))


def _migrate_template_colors() -> None:
    insp = inspect(engine)
    if "expense_templates" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("expense_templates")}
    if "color" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE expense_templates ADD COLUMN color VARCHAR(7) NOT NULL DEFAULT '#6366f1'"))
        rows = conn.execute(text("SELECT id FROM expense_templates ORDER BY id")).fetchall()
        used: set[str] = set()
        for (tid,) in rows:
            c = _next_palette_color(used)
            used.add(c)
            conn.execute(text("UPDATE expense_templates SET color = :c WHERE id = :id"), {"c": c, "id": tid})


def _migrate_savings_to_records() -> None:
    insp = inspect(engine)
    if "periods" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("periods")}

    if "savings" in cols and "savings" not in insp.get_table_names():
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS savings ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "period_id INTEGER NOT NULL REFERENCES periods(id) ON DELETE CASCADE, "
                "title VARCHAR(255) NOT NULL DEFAULT 'Накопления', "
                "amount FLOAT NOT NULL DEFAULT 0.0)"
            ))
            rows = conn.execute(text("SELECT id, savings FROM periods WHERE savings > 0")).fetchall()
            for pid, amount in rows:
                conn.execute(text(
                    "INSERT INTO savings (period_id, title, amount) VALUES (:pid, 'Накопления', :amt)"
                ), {"pid": pid, "amt": amount})
            conn.execute(text("ALTER TABLE periods DROP COLUMN savings"))
    elif "savings" in cols and "savings" in insp.get_table_names():
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT id, savings FROM periods WHERE savings > 0")).fetchall()
            for pid, amount in rows:
                conn.execute(text(
                    "INSERT INTO savings (period_id, title, amount) VALUES (:pid, 'Накопления', :amt)"
                ), {"pid": pid, "amt": amount})
            conn.execute(text("ALTER TABLE periods DROP COLUMN savings"))


