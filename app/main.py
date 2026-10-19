from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analysis, db
from .categorize import CATEGORIES
from .service import import_bytes, recategorize, set_category

BASE = Path(__file__).parent
app = FastAPI(title="Budget")
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


def _back(request: Request, default: str) -> RedirectResponse:
    return RedirectResponse(request.headers.get("referer") or default, status_code=303)


@app.get("/")
def dashboard(request: Request):
    con = db.connect()
    txns = _load(con)
    rec = analysis.detect_recurring(txns)
    table = analysis.monthly_table(txns, {r["key"] for r in rec})
    planned = [dict(r) for r in con.execute("SELECT * FROM planned ORDER BY date")]
    settings = db.get_settings(con)
    s = analysis.summary(table, settings, planned, date.today())
    return templates.TemplateResponse(request, "dashboard.html", {
        "s": s, "table": table[-13:][::-1], "planned": planned, "settings": settings,
        "recurring": rec, "empty": not txns, "page": "dashboard",
    })


@app.get("/transactions")
def transactions(request: Request, m: str = "", q: str = "", cat: str = "", review: int = 0):
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
    if review:
        sql += " AND source='bank' AND category IN ('À catégoriser','Autres rentrées','PayPal (à détailler)','Famille & amis')"
    rows = con.execute(sql + " ORDER BY date DESC, id DESC LIMIT 500", args).fetchall()
    return templates.TemplateResponse(request, "transactions.html", {
        "rows": rows, "months": months, "m": m, "q": q, "cat": cat, "review": review, "page": "transactions"})


@app.post("/transactions/{tx_id}/category")
def update_category(request: Request, tx_id: int, category: str = Form(...), apply_all: str = Form("")):
    if category in CATEGORIES:
        set_category(db.connect(), tx_id, category, bool(apply_all))
    return _back(request, "/transactions")


@app.get("/recurring")
def recurring(request: Request):
    txns = _load(db.connect())
    return templates.TemplateResponse(request, "recurring.html", {
        "rec": analysis.detect_recurring(txns), "page": "recurring"})


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
