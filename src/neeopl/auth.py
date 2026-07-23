import hmac
import secrets

import bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .database import load_config, save_config
from .models import User

SECRET_KEY = load_config().get("secret_key") or secrets.token_hex(32)
if not load_config().get("secret_key"):
    cfg = load_config()
    cfg["secret_key"] = SECRET_KEY
    save_config(cfg)

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="neeopl-session")

COOKIE_NAME = "neeopl_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30

CSRF_COOKIE_NAME = "neeopl_csrf"
CSRF_HEADER = "X-CSRF-Token"


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_session_cookie(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def verify_session_cookie(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data.get("uid")
    except BadSignature:
        return None


def generate_csrf_token() -> str:
    return secrets.token_hex(32)


def verify_csrf_token(cookie_token: str | None, form_token: str | None) -> bool:
    if not cookie_token or not form_token:
        return False
    return hmac.compare_digest(cookie_token, form_token)


def get_user_by_username(db, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def has_admin(db) -> bool:
    return db.query(User).count() > 0


def create_admin(db, username: str, password: str) -> User:
    user = User(username=username, password_hash=hash_password(password), is_admin=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user