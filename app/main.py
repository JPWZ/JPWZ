import asyncio
import base64
import hmac
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analysis, db
from .categorize import CATEGORIES
from .service import import_bytes, recategorize, set_category

BASE = Path(__file__).parent
app = FastAPI(title="Budget")

# Accès protégé par mot de passe dès que APP_PASSWORD est défini (obligatoire si APP_PUBLIC=1).
if os.environ.get("APP_PUBLIC") == "1" and not os.environ.get("APP_PASSWORD"):
    raise RuntimeError("APP_PUBLIC=1 exige APP_PASSWORD : refus de démarrer sans mot de passe.")


@app.middleware("http")
async def require_password(request: Request, call_next):
    password = os.environ.get("APP_PASSWORD")
    if not password:
        return await call_next(request)
    given = ""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            given = base64.b64decode(header[6:]).decode().partition(":")[2]
        except Exception:
            given = ""
    if given and hmac.compare_digest(given.encode(), password.encode()):
        return await call_next(request)
    await asyncio.sleep(1)  # freine les essais répétés
    return Response("Authentification requise", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Budget", charset="UTF-8"'})

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def eur(cents, signed=False) -> str:
    v = round((cents or 0) / 100)
    s = f"{abs(v):,}".replace(",", " ")
    sign = "-" if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}{s} €"


def month_label(m: str) -> str:
    y, mm = m.split("-")
    return f"{MONTHS_FR[int(mm) - 1]} {y}"


templates.env.filters["eur"] = eur
templates.env.filters["month_label"] = month_label
templates.env.globals["CATEGORIES"] = CATEGORIES


def _load(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM transactions ORDER BY date, id")]


def _analysis(con):
    txns = _load(con)
    ov = {r["key"]: r["bucket"] for r in con.execute("SELECT * FROM key_overrides")}
    rec = analysis.detect_recurring(txns)
    force_var = {k for k, b in ov.items() if b == "variable"}
    keys = ({r["key"] for r in rec} - force_var) | {k for k, b in ov.items() if b == "fixed"}
    table = analysis.monthly_table(txns, keys, force_var)
    return txns, rec, keys, force_var, table, ov


def _back(request: Request, default: str) -> RedirectResponse:
    return RedirectResponse(request.headers.get("referer") or default, status_code=303)


@app.get("/")
def dashboard(request: Request):
    con = db.connect()
    txns, rec, keys, force_var, table, ov = _analysis(con)
    planned = [dict(r) for r in con.execute("SELECT * FROM planned ORDER BY date")]
    settings = db.get_settings(con)
    s = analysis.summary(table, settings, planned, date.today())
    window = [r["month"] for r in table if not r["partial"]][-12:]
    bd = analysis.breakdown(txns, keys, window, force_var, ov)
    return templates.TemplateResponse(request, "dashboard.html", {
        "s": s, "table": table[-13:][::-1], "planned": planned, "settings": settings,
        "bd": bd, "n": len(window) or 1, "month": None, "empty": not txns, "page": "dashboard",
    })


@app.get("/month/{m}")
def month_detail(request: Request, m: str):
    con = db.connect()
    txns, rec, keys, force_var, table, ov = _analysis(con)
    months = [r["month"] for r in table]
    if m not in months:
        return RedirectResponse("/", status_code=303)
    i = months.index(m)
    bd = analysis.breakdown(txns, keys, [m], force_var, ov)
    return templates.TemplateResponse(request, "month.html", {
        "r": table[i], "bd": bd, "n": 1, "month": m, "page": "dashboard",
        "prev": months[i - 1] if i > 0 else None, "next": months[i + 1] if i + 1 < len(months) else None})


@app.post("/override")
def override(request: Request, key: str = Form(...), bucket: str = Form(...)):
    con = db.connect()
    with con:
        if bucket in ("fixed", "variable"):
            con.execute("INSERT OR REPLACE INTO key_overrides(key, bucket) VALUES (?,?)", (key, bucket))
        else:
            con.execute("DELETE FROM key_overrides WHERE key=?", (key,))
    return _back(request, "/")


@app.get("/transactions")
def transactions(request: Request, m: str = "", q: str = "", cat: str = "", review: int = 0, key: str = ""):
    con = db.connect()
    months = [r[0] for r in con.execute("SELECT DISTINCT substr(date,1,7) FROM transactions ORDER BY 1 DESC")]
    m = m or (months[0] if months else "")
    sql, args = "SELECT * FROM transactions WHERE 1=1", []
    if m != "all":
        sql += " AND substr(date,1,7)=?"; args.append(m)
    if q:
        sql += " AND (label LIKE ? OR info LIKE ?)"; args += [f"%{q}%"] * 2
    if cat:
        sql += " AND category=?"; args.append(cat)
    if key:
        sql += " AND key=?"; args.append(key)
    if review:
        sql += " AND source='bank' AND category IN ('À catégoriser','Autres rentrées','PayPal (à détailler)','Famille & amis')"
    rows = con.execute(sql + " ORDER BY date DESC, id DESC LIMIT 500", args).fetchall()
    return templates.TemplateResponse(request, "transactions.html", {
        "rows": rows, "months": months, "m": m, "q": q, "cat": cat, "review": review, "key": key,
        "total": sum(r["amount_cents"] for r in rows), "page": "transactions"})


@app.post("/transactions/{tx_id}/category")
def update_category(request: Request, tx_id: int, category: str = Form(...), apply_all: str = Form("")):
    if category in CATEGORIES:
        set_category(db.connect(), tx_id, category, bool(apply_all))
    return _back(request, "/transactions")


@app.get("/recurring")
def recurring(request: Request):
    con = db.connect()
    txns, rec, keys, force_var, table, ov = _analysis(con)
    return templates.TemplateResponse(request, "recurring.html", {"rec": rec, "ov": ov, "page": "recurring"})


@app.get("/settings")
def settings_page(request: Request, msg: str = ""):
    con = db.connect()
    n = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    return templates.TemplateResponse(request, "settings.html", {
        "settings": db.get_settings(con), "n": n, "msg": msg, "page": "settings"})


@app.post("/settings")
def save_settings(epargne_cible: float = Form(...), livret_a_solde: float = Form(...)):
    con = db.connect()
    with con:
        for k, v in (("epargne_cible", epargne_cible), ("livret_a_solde", livret_a_solde)):
            con.execute("INSERT OR REPLACE INTO settings(name, value) VALUES (?,?)", (k, str(v)))
    return RedirectResponse("/settings?msg=Réglages+enregistrés", status_code=303)


@app.post("/import")
async def import_file(file: UploadFile = File(...)):
    con = db.connect()
    try:
        added, total = import_bytes(con, await file.read())
        msg = f"{added} nouvelles opérations ({total} lues)."
    except ValueError as e:
        msg = str(e)
    return RedirectResponse(f"/settings?msg={msg}", status_code=303)


@app.post("/recategorize")
def recat():
    n = recategorize(db.connect())
    return RedirectResponse(f"/settings?msg={n}+opérations+recatégorisées", status_code=303)


@app.post("/planned")
def add_planned(label: str = Form(...), date_: str = Form(..., alias="date"), amount: float = Form(...)):
    con = db.connect()
    with con:
        con.execute("INSERT INTO planned(label, date, amount_cents) VALUES (?,?,?)",
                    (label, date_, round(amount * 100)))
    return RedirectResponse("/", status_code=303)


@app.post("/planned/{pid}/delete")
def del_planned(pid: int):
    con = db.connect()
    with con:
        con.execute("DELETE FROM planned WHERE id=?", (pid,))
    return RedirectResponse("/", status_code=303)
