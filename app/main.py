import asyncio
import base64
import re
import unicodedata
from collections import Counter
import hmac
import os
from datetime import date
from pathlib import Path

from typing import List

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analysis, db
from .categorize import CATEGORIES
from .ui import ICONS, category_style
from .service import import_any, recategorize, set_category

BASE = Path(__file__).parent
app = FastAPI(title="Budget")

# Accès protégé par mot de passe dès que APP_PASSWORD est défini (obligatoire si APP_PUBLIC=1).
if os.environ.get("APP_PUBLIC") == "1" and not os.environ.get("APP_PASSWORD"):
    raise RuntimeError("APP_PUBLIC=1 exige APP_PASSWORD : refus de démarrer sans mot de passe.")


@app.middleware("http")
async def require_password(request: Request, call_next):
    password = os.environ.get("APP_PASSWORD")
    if not password or request.url.path == "/health":
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

MONTHS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
               "octobre", "novembre", "décembre"]
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
templates.env.filters["month_long"] = lambda m: f"{MONTHS_LONG[int(m[5:7]) - 1].capitalize()} {m[:4]}"
templates.env.globals["ICONS"] = ICONS
templates.env.globals["category_style"] = category_style
templates.env.globals["user_name"] = os.environ.get("BUDGET_USER", "Jean-Philippe")
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


@app.get("/health")
def health():
    return {"status": "ok"}


def _slug(text: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or "poste"


@app.get("/")
def dashboard(request: Request, m: str = ""):
    con = db.connect()
    txns, rec, keys, force_var, table, ov = _analysis(con)
    planned = [dict(r) for r in con.execute("SELECT * FROM planned ORDER BY date")]
    settings = db.get_settings(con)
    s = analysis.summary(table, settings, planned, date.today())
    window = [r["month"] for r in table if not r["partial"]][-12:]
    bd = analysis.breakdown(txns, keys, window, force_var, ov)
    ctx = {"s": s, "table": table[-13:][::-1], "planned": planned, "settings": settings,
           "bd": bd, "n": len(window) or 1, "month": None, "empty": not txns, "page": "dashboard"}
    if table:
        months = [r["month"] for r in table]
        sel = m if m in months else months[-1]
        i = months.index(sel)
        row = table[i]
        gross = lambda r: r["fixed"] + r["variable"] + r["exceptional"] + r["household"]
        similar = Counter(t["key"] for t in txns)
        by_cat: dict[str, dict] = {}
        for t in txns:
            if t["date"][:7] == sel and t["kind"] in ("expense", "household"):
                g = by_cat.setdefault(t["category"], {"category": t["category"], "total": 0, "count": 0, "ops": []})
                g["total"] -= t["amount_cents"]
                g["count"] += 1
                g["ops"].append({"id": t["id"], "date": t["date"], "label": t["label"], "category": t["category"],
                                 "amount": -t["amount_cents"], "similar": similar[t["key"]] - 1})
        postes = sorted((g for g in by_cat.values() if g["total"] > 0), key=lambda g: -g["total"])
        if len(postes) > 9:
            rest = postes[8:]
            postes = postes[:8] + [{"category": "Autres", "total": sum(g["total"] for g in rest),
                                    "count": sum(g["count"] for g in rest), "detail": ", ".join(g["category"] for g in rest),
                                    "ops": [o for g in rest for o in g["ops"]]}]
        for g in postes:
            g["slug"] = _slug(g["category"])
            g["ops"].sort(key=lambda o: (o["date"], o["id"]), reverse=True)
        chart = table[-12:]
        prev_gross = gross(table[i - 1]) if i > 0 else 0
        ctx.update({
            "sel": row, "sel_month": sel, "prev_m": months[i - 1] if i > 0 else None,
            "next_m": months[i + 1] if i + 1 < len(months) else None, "postes": postes,
            "postes_max": postes[0]["total"] if postes else 1, "gross": gross(row),
            "delta_pct": round((gross(row) - prev_gross) / prev_gross * 100) if prev_gross else None,
            "prev_label": MONTHS_LONG[int(months[i - 1][5:7]) - 1] if i > 0 else "",
            "chart": chart, "chart_max": max((gross(r) for r in chart), default=1) or 1,
            "chart_total": sum(gross(r) for r in chart), "income_m": row["income"] + row["income_other"]})
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/extras")
def extras_page(request: Request, m: str = ""):
    con = db.connect()
    txns, rec, keys, force_var, table, ov = _analysis(con)
    flags = {r["poste"]: r["flag"] for r in con.execute("SELECT * FROM poste_flags")}
    data = analysis.extras(txns, keys, force_var, flags, m or None)
    return templates.TemplateResponse(request, "extras.html", {"d": data, "empty": not txns, "page": "extras"})


@app.post("/flag")
def flag(request: Request, poste: str = Form(...), flag: str = Form(...)):
    con = db.connect()
    with con:
        if flag in ("essential", "discretionary"):
            con.execute("INSERT OR REPLACE INTO poste_flags(poste, flag) VALUES (?,?)", (poste, flag))
        else:
            con.execute("DELETE FROM poste_flags WHERE poste=?", (poste,))
    return _back(request, "/extras")


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
def transactions(request: Request, m: str = "", q: str = "", cat: str = "", review: int = 0, key: str = "", sub: str = ""):
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
    if sub:
        sql += " AND bank_sub=?"; args.append(sub)
    if review:
        sql += " AND source='bank' AND category IN ('À catégoriser','Autres rentrées','PayPal (à détailler)','Famille & amis')"
    rows = con.execute(sql + " ORDER BY date DESC, id DESC LIMIT 500", args).fetchall()
    return templates.TemplateResponse(request, "transactions.html", {
        "rows": rows, "months": months, "m": m, "q": q, "cat": cat, "review": review, "key": key,
        "total": sum(r["amount_cents"] for r in rows), "page": "transactions"})


@app.post("/transactions/{tx_id}/category")
def update_category(request: Request, tx_id: int, category: str = Form(...), apply_all: str = Form(""),
                    next: str = Form("")):
    if category in CATEGORIES:
        set_category(db.connect(), tx_id, category, bool(apply_all))
    if next.startswith("/") and not next.startswith("//"):
        return RedirectResponse(next, status_code=303)
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


@app.get("/backup")
def backup():
    """Copie cohérente de la base (corrections, réglages, engagements inclus)."""
    import sqlite3, tempfile
    src = db.connect()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    dst = sqlite3.connect(tmp.name)
    src.backup(dst)
    dst.close()
    return FileResponse(tmp.name, filename=f"budget-{date.today().isoformat()}.db",
                        background=BackgroundTask(os.unlink, tmp.name))


@app.post("/import")
async def import_file(files: List[UploadFile] = File(...)):
    con = db.connect()
    msgs = []
    for f in files:
        try:
            msgs.append(f"{f.filename} : {import_any(con, await f.read())}")
        except ValueError as e:
            msgs.append(f"{f.filename} : {e}")
    return RedirectResponse("/settings?msg=" + " — ".join(msgs), status_code=303)


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
