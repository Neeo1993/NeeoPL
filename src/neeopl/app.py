import os
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from .auth import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER,
    create_admin,
    create_session_cookie,
    generate_csrf_token,
    get_user_by_username,
    has_admin,
    verify_csrf_token,
    verify_password,
    verify_session_cookie,
)
from .database import (
    SessionLocal,
    get_currency_symbol,
    get_db_path,
    init_db,
    set_db_path,
)
from .models import Expense, Income, Saving
from . import crud

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
SOURCE_DIR = os.path.join(BASE_DIR, "source")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def _money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        n = 0.0
    symbol = get_currency_symbol()
    s = f"{n:,.2f}".replace(",", "\u202f")
    if symbol in ("$", "€"):
        return f"{symbol}{s}"
    return f"{s}\u00a0{symbol}"

templates.env.filters["money"] = _money

@contextmanager
def db_scope():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _to_float(v) -> float:
    if v is None or str(v).strip() == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0

def create_app() -> FastAPI:
    app = FastAPI(title="NeeoP&L", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/source", StaticFiles(directory=SOURCE_DIR), name="source")

    templates.env.globals["currency_symbol"] = get_currency_symbol()

    def _csrf_field(request: Request) -> Markup:
        token = ""
        if hasattr(request, "state"):
            token = getattr(request.state, "csrf_token", "")
        if not token:
            token = request.cookies.get(CSRF_COOKIE_NAME, "")
        return Markup(f'<input type="hidden" name="csrf_token" value="{token}"/>')

    templates.env.globals["csrf_field"] = _csrf_field

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    def _unauthorized() -> HTMLResponse:
        resp = HTMLResponse("", status_code=401)
        resp.headers["HX-Redirect"] = "/login"
        return resp

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if path.startswith("/source"):
            return await call_next(request)

        with db_scope() as db:
            admin_exists = has_admin(db)

        if not admin_exists:
            if path == "/setup":
                return await call_next(request)
            resp = RedirectResponse(url="/setup", status_code=303)
            if method != "GET" and request.headers.get("HX-Request") == "true":
                resp = HTMLResponse("", status_code=401)
                resp.headers["HX-Redirect"] = "/setup"
            return resp

        if admin_exists and path == "/setup":
            return RedirectResponse(url="/login", status_code=303)

        if path == "/login":
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        uid = verify_session_cookie(token) if token else None
        if not uid:
            if request.headers.get("HX-Request") == "true":
                return _unauthorized()
            return RedirectResponse(url="/login", status_code=303)

        if method in ("POST", "PUT", "PATCH", "DELETE") and path != "/login":
            cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
            header_csrf = request.headers.get(CSRF_HEADER)
            if verify_csrf_token(cookie_csrf, header_csrf):
                request.state.uid = uid
                request.state.csrf_token = cookie_csrf or ""
                return await call_next(request)
            body = await request.body()
            params = parse_qs(body.decode("utf-8", errors="replace"))
            form_csrf = (params.get("csrf_token") or [""])[0]
            if not verify_csrf_token(cookie_csrf, form_csrf):
                if request.headers.get("HX-Request") == "true":
                    resp = HTMLResponse("CSRF-токен недействителен", status_code=403)
                    resp.headers["HX-Redirect"] = "/login"
                    return resp
                return HTMLResponse("CSRF-токен недействителен", status_code=403)

            async def _receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request.scope["receive"] = _receive

        request.state.uid = uid
        request.state.csrf_token = request.cookies.get(CSRF_COOKIE_NAME, "")
        return await call_next(request)

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_form(request: Request):
        with db_scope() as db:
            if has_admin(db):
                return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(request, "setup.html", {})

    @app.post("/setup")
    async def setup_create(request: Request):
        form = await request.form()
        username = form.get("username", "").strip()
        password = form.get("password", "")
        if not username or not password:
            return HTMLResponse("Логин и пароль обязательны", status_code=400)
        with db_scope() as db:
            if has_admin(db):
                return RedirectResponse(url="/login", status_code=303)
            create_admin(db, username, password)
        resp = RedirectResponse(url="/", status_code=303)
        return resp

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html", {})

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        username = form.get("username", "").strip()
        password = form.get("password", "")
        with db_scope() as db:
            user = get_user_by_username(db, username)
            if user and verify_password(password, user.password_hash):
                resp = RedirectResponse(url="/", status_code=303)
                resp.set_cookie(
                    COOKIE_NAME,
                    create_session_cookie(user.id),
                    max_age=COOKIE_MAX_AGE,
                    httponly=True,
                    samesite="strict",
                )
                csrf = generate_csrf_token()
                resp.set_cookie(
                    CSRF_COOKIE_NAME,
                    csrf,
                    max_age=COOKIE_MAX_AGE,
                    httponly=False,
                    samesite="strict",
                )
                return resp
        return templates.TemplateResponse(
            request, "login.html", {"error": "Неверный логин или пароль"}, status_code=401
        )

    @app.post("/logout")
    async def logout(request: Request):
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie(COOKIE_NAME)
        return resp

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        with db_scope() as db:
            periods = crud.list_periods(db)
            data = [
                {
                    "id": p.id,
                    "year": p.year,
                    "month": p.month,
                    "title": p.title,
                    "total_income": p.total_income,
                    "total_plan": p.total_plan,
                    "total_fact": p.total_fact,
                    "total_savings": p.total_savings,
                    "delta_income_plan": p.delta_income_plan,
                    "delta_income_fact": p.delta_income_fact,
                }
                for p in periods
            ]
            totals = {
                "income": round(sum(p.total_income for p in periods), 2),
                "plan": round(sum(p.total_plan for p in periods), 2),
                "fact": round(sum(p.total_fact for p in periods), 2),
                "savings": round(sum(p.total_savings for p in periods), 2),
            }
        return templates.TemplateResponse(
            request, "index.html", {"periods": data, "totals": totals}
        )

    @app.get("/periods/{period_id}", response_class=HTMLResponse)
    async def period_detail(request: Request, period_id: int):
        with db_scope() as db:
            data = _snapshot(db, period_id)
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(request, "period.html", {"period": data})

    @app.get("/periods/{period_id}/body", response_class=HTMLResponse)
    async def period_body(request: Request, period_id: int):
        with db_scope() as db:
            data = _snapshot(db, period_id)
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.post("/periods")
    async def period_create(request: Request):
        form = await request.form()
        month = int(form.get("month", 1))
        year = int(form.get("year", 2026))
        note = form.get("note", "")
        with db_scope() as db:
            crud.create_period(db, month, year, note)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/periods/{period_id}/delete")
    async def period_delete(period_id: int):
        with db_scope() as db:
            crud.delete_period(db, period_id)
        return RedirectResponse(url="/", status_code=303)

    def _snapshot(db, period_id):
        db.expire_all()
        p = crud.get_period(db, period_id)
        if not p:
            return None
        return {
            "id": p.id,
            "month": p.month,
            "year": p.year,
            "note": p.note,
            "title": p.title,
            "total_income": p.total_income,
            "total_plan": p.total_plan,
            "total_fact": p.total_fact,
            "total_savings": p.total_savings,
            "delta_expenses": p.delta_expenses,
            "delta_income_plan": p.delta_income_plan,
            "delta_income_fact": p.delta_income_fact,
            "incomes": [
                {"id": i.id, "title": i.title, "amount": i.amount}
                for i in p.incomes
            ],
            "savings": [
                {"id": s.id, "title": s.title, "amount": s.amount}
                for s in p.savings
            ],
            "expenses": [
                {
                    "id": e.id,
                    "title": e.title,
                    "plan": e.plan,
                    "fact": e.fact,
                    "delta": e.delta,
                    "done": e.done,
                }
                for e in p.expenses
            ],
            "chart": [
                {"title": e.title, "fact": e.fact, "type": "expense", "color": crud.get_template_color(db, e.title)}
                for e in p.expenses
                if e.fact > 0
            ] + [
                {"title": "Сбережения", "fact": p.total_savings, "type": "savings", "color": "#8b5cf6"},
                {"title": "Иные расходы", "fact": p.delta_income_fact, "type": "delta", "color": "#64748b"},
            ],
            "expense_templates": [
                {"id": t.id, "title": t.title, "plan": t.plan}
                for t in crud.list_expense_templates(db)
            ],
            "total_all_savings": round(
                sum(per.total_savings for per in crud.list_periods(db)), 2
            ),
        }

    @app.post("/periods/{period_id}/incomes", response_class=HTMLResponse)
    async def income_create(request: Request, period_id: int):
        form = await request.form()
        title = form.get("title", "")
        amount = _to_float(form.get("amount"))
        with db_scope() as db:
            crud.add_income(db, period_id, title, amount)
            data = _snapshot(db, period_id)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.post("/periods/{period_id}/savings", response_class=HTMLResponse)
    async def saving_create(request: Request, period_id: int):
        form = await request.form()
        title = form.get("title", "Накопления")
        amount = _to_float(form.get("amount"))
        with db_scope() as db:
            crud.add_saving(db, period_id, title, amount)
            data = _snapshot(db, period_id)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.post("/periods/{period_id}/expenses", response_class=HTMLResponse)
    async def expense_create(request: Request, period_id: int):
        form = await request.form()
        title = form.get("title", "")
        plan = _to_float(form.get("plan"))
        fact = _to_float(form.get("fact"))
        with db_scope() as db:
            crud.add_expense(db, period_id, title, plan, fact)
            crud.get_or_create_expense_template(db, title, plan)
            data = _snapshot(db, period_id)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.delete("/incomes/{income_id}", response_class=HTMLResponse)
    async def income_delete(request: Request, income_id: int):
        with db_scope() as db:
            inc = db.get(Income, income_id)
            pid = inc.period_id if inc else None
            crud.delete_income(db, income_id)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("", status_code=204)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.delete("/savings/{saving_id}", response_class=HTMLResponse)
    async def saving_delete(request: Request, saving_id: int):
        with db_scope() as db:
            sv = db.get(Saving, saving_id)
            pid = sv.period_id if sv else None
            crud.delete_saving(db, saving_id)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("", status_code=204)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.delete("/expenses/{expense_id}", response_class=HTMLResponse)
    async def expense_delete(request: Request, expense_id: int):
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            pid = exp.period_id if exp else None
            crud.delete_expense(db, expense_id)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("", status_code=204)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.get("/incomes/{income_id}/edit", response_class=HTMLResponse)
    async def income_edit(request: Request, income_id: int):
        with db_scope() as db:
            inc = db.get(Income, income_id)
            data = (
                {
                    "id": inc.id,
                    "title": inc.title,
                    "amount": inc.amount,
                    "period_id": inc.period_id,
                }
                if inc
                else None
            )
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/income_edit_row.html", {"i": data}
        )

    @app.post("/incomes/{income_id}", response_class=HTMLResponse)
    async def income_update(request: Request, income_id: int):
        form = await request.form()
        title = form.get("title", "")
        amount = _to_float(form.get("amount"))
        with db_scope() as db:
            inc = db.get(Income, income_id)
            pid = inc.period_id if inc else None
            if inc:
                crud.update_income(db, income_id, title, amount)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.get("/savings/{saving_id}/edit", response_class=HTMLResponse)
    async def saving_edit(request: Request, saving_id: int):
        with db_scope() as db:
            sv = db.get(Saving, saving_id)
            data = (
                {
                    "id": sv.id,
                    "title": sv.title,
                    "amount": sv.amount,
                    "period_id": sv.period_id,
                }
                if sv
                else None
            )
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/saving_edit_row.html", {"s": data}
        )

    @app.post("/savings/{saving_id}", response_class=HTMLResponse)
    async def saving_update(request: Request, saving_id: int):
        form = await request.form()
        title = form.get("title", "Накопления")
        amount = _to_float(form.get("amount"))
        with db_scope() as db:
            sv = db.get(Saving, saving_id)
            pid = sv.period_id if sv else None
            if sv:
                crud.update_saving(db, saving_id, title, amount)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.post("/periods/{period_id}/dip-savings", response_class=HTMLResponse)
    async def dip_savings(request: Request, period_id: int):
        form = await request.form()
        amount = _to_float(form.get("amount"))
        with db_scope() as db:
            p = crud.get_period(db, period_id)
            if not p:
                return HTMLResponse("Не найдено", status_code=404)
            available = round(
                sum(per.total_savings for per in crud.list_periods(db)), 2
            )
            if amount > 0:
                amount = min(amount, max(available, 0.0))
                if amount > 0:
                    crud.add_income(db, period_id, "Из накоплений", amount)
                    crud.add_saving(db, period_id, "Залез в накопления", -amount)
            data = _snapshot(db, period_id)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.get("/expenses/{expense_id}/edit", response_class=HTMLResponse)
    async def expense_edit(request: Request, expense_id: int):
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            data = (
                {
                    "id": exp.id,
                    "title": exp.title,
                    "plan": exp.plan,
                    "fact": exp.fact,
                    "period_id": exp.period_id,
                }
                if exp
                else None
            )
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/expense_edit_row.html", {"e": data}
        )

    @app.post("/expenses/{expense_id}", response_class=HTMLResponse)
    async def expense_update(request: Request, expense_id: int):
        form = await request.form()
        title = form.get("title", "")
        plan = _to_float(form.get("plan"))
        fact = _to_float(form.get("fact"))
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            pid = exp.period_id if exp else None
            if exp:
                crud.update_expense(db, expense_id, title, plan, fact)
                crud.get_or_create_expense_template(db, title, plan)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.get("/expenses/{expense_id}/add-fact", response_class=HTMLResponse)
    async def expense_add_fact_form(request: Request, expense_id: int):
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            data = (
                {
                    "id": exp.id,
                    "title": exp.title,
                    "fact": exp.fact,
                    "period_id": exp.period_id,
                }
                if exp
                else None
            )
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/expense_add_fact_row.html", {"e": data}
        )

    @app.post("/expenses/{expense_id}/add-fact", response_class=HTMLResponse)
    async def expense_add_fact(request: Request, expense_id: int):
        form = await request.form()
        amount = _to_float(form.get("amount"))
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            pid = exp.period_id if exp else None
            if exp and amount > 0:
                crud.add_fact_with_history(db, expense_id, amount)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.post("/expenses/{expense_id}/toggle-done", response_class=HTMLResponse)
    async def expense_toggle_done(request: Request, expense_id: int):
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            pid = exp.period_id if exp else None
            if exp:
                crud.toggle_expense_done(db, expense_id)
            data = _snapshot(db, pid) if pid else None
        if not data:
            return HTMLResponse("Не найдено", status_code=404)
        return templates.TemplateResponse(
            request, "partials/period_body.html", {"period": data}
        )

    @app.get("/expenses/{expense_id}/history", response_class=HTMLResponse)
    async def expense_history(request: Request, expense_id: int):
        with db_scope() as db:
            exp = db.get(Expense, expense_id)
            if not exp:
                return HTMLResponse("Не найдено", status_code=404)
            title = exp.title
            period_id = exp.period_id
            additions = [
                {"amount": a.amount, "created_at": a.created_at}
                for a in crud.list_fact_additions(db, expense_id)
            ]
        return templates.TemplateResponse(
            request, "partials/expense_history.html",
            {"expense_id": expense_id, "period_id": period_id, "title": title, "additions": additions}
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings(request: Request):
        from .database import CURRENCIES, get_currency

        db_path = get_db_path()
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "db_path": str(db_path),
                "db_exists": db_path.exists(),
                "currencies": CURRENCIES,
                "current_currency": get_currency(),
            },
        )

    @app.post("/settings/db-path")
    async def change_db_path(request: Request):
        form = await request.form()
        new_path = form.get("db_path", "").strip()
        if not new_path:
            return RedirectResponse(url="/settings", status_code=303)
        move = form.get("move") == "1"
        try:
            set_db_path(Path(new_path), move_data=move)
        except (OSError, ValueError) as e:
            return HTMLResponse(f"Ошибка: {escape(str(e))}", status_code=400)
        _restart_server()
        return RedirectResponse(url="/settings", status_code=303)

    @app.post("/settings/currency")
    async def change_currency(request: Request):
        from .database import set_currency

        form = await request.form()
        code = form.get("currency", "RUB")
        set_currency(code)
        _restart_server()
        return RedirectResponse(url="/settings", status_code=303)

    def _restart_server() -> None:
        plist = os.path.expanduser("~/Library/LaunchAgents/ai.neeopl.server.plist")

        def _do_restart():
            time.sleep(1)
            if os.path.exists(plist):
                try:
                    subprocess.run(
                        ["launchctl", "kickstart", "-k", "gui/$(id -u)/ai.neeopl.server"],
                        check=False,
                    )
                except Exception:
                    pass
            os._exit(0)

        threading.Thread(target=_do_restart, daemon=True).start()

    return app