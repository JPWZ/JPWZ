"""Calculs : récurrents, tableau mensuel, capacité d'épargne."""
import calendar
import statistics
from collections import defaultdict
from datetime import date, timedelta

from .categorize import LOISIR_CATEGORIES

EXCEPTIONAL_CENTS = 40000  # une dépense isolée >= 400 € est "exceptionnelle"
PRIME_FACTOR = 1.25        # un salaire > 1,25 x salaire de base contient une prime


def _month(d: str) -> str:
    return d[:7]


def detect_recurring(txns: list[dict]) -> list[dict]:
    """Prélèvements/paiements réguliers : présents dans la majorité des mois,
    au plus 2 fois par mois, avec un montant stable (ou un prélèvement/prêt)."""
    if not txns:
        return []
    months = sorted({_month(t["date"]) for t in txns})
    n_months = len(months)
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        if t["kind"] in ("expense", "household") and t["amount_cents"] < 0:
            groups[t["key"]].append(t)
    out = []
    for key, items in groups.items():
        per_month: dict[str, int] = defaultdict(int)
        for t in items:
            per_month[_month(t["date"])] += 1
        present = len(per_month)
        scheduled = all(t["bank_type"] in ("Prelevement", "Pret") for t in items)
        if present < 3 or present < 0.5 * n_months:
            continue
        if items[-1]["category"] == "PayPal (à détailler)":
            continue
        if max(per_month.values()) > (4 if scheduled else 2):
            continue
        amounts = [-t["amount_cents"] for t in items]
        mean = statistics.fmean(amounts)
        cv = statistics.pstdev(amounts) / mean if mean else 1
        if cv > 0.2 and not scheduled:
            continue
        dates = sorted(date.fromisoformat(t["date"]) for t in items)
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        gap = int(statistics.median(gaps)) if gaps else 30
        out.append({
            "key": key,
            "id": items[-1].get("id"),
            "label": items[-1]["label"],
            "category": items[-1]["category"],
            "kind": items[-1]["kind"],
            "months": present,
            "count": len(items),
            "avg_cents": round(mean),
            "stable": cv <= 0.05,
            "last_date": dates[-1].isoformat(),
            "next_date": (dates[-1] + timedelta(days=gap if 20 <= gap <= 40 else 30)).isoformat(),
            "monthly_cents": round(sum(amounts) / n_months),
        })
    return sorted(out, key=lambda r: -r["monthly_cents"])


def _is_partial(month: str, last_date: date) -> bool:
    y, m = map(int, month.split("-"))
    return (last_date.year, last_date.month) == (y, m) and last_date.day < calendar.monthrange(y, m)[1]


def monthly_table(txns: list[dict], recurring_keys: set[str]) -> list[dict]:
    if not txns:
        return []
    last = date.fromisoformat(max(t["date"] for t in txns))
    salaries = [t["amount_cents"] for t in txns if t["kind"] == "salary" and t["amount_cents"] > 0]
    base = int(statistics.median(salaries)) if salaries else 0
    rows: dict[str, dict] = {}
    keys = ["salary_base", "prime", "income_other", "reimbursement", "fixed", "variable",
            "exceptional", "household", "invest", "savings_in", "savings_out", "loan_in", "loisir"]
    for t in txns:
        m = _month(t["date"])
        r = rows.setdefault(m, {k: 0 for k in keys} | {"month": m})
        a, kind = t["amount_cents"], t["kind"]
        if kind == "salary":
            if base and a > PRIME_FACTOR * base:
                r["salary_base"] += base
                r["prime"] += a - base
            else:
                r["salary_base"] += a
        elif kind in ("income_other", "reimbursement", "loan_in"):
            r[{"income_other": "income_other", "reimbursement": "reimbursement", "loan_in": "loan_in"}[kind]] += a
        elif kind == "household":
            r["household"] -= a
        elif kind == "invest":
            r["invest"] -= a
        elif kind == "savings_move":
            r["savings_in" if a > 0 else "savings_out"] += abs(a)
        else:  # expense
            if t["key"] in recurring_keys:
                r["fixed"] -= a
            elif a <= -EXCEPTIONAL_CENTS:
                r["exceptional"] -= a
            else:
                r["variable"] -= a
            if t["category"] in LOISIR_CATEGORIES:
                r["loisir"] -= a
    table = []
    for m in sorted(rows):
        r = rows[m]
        r["partial"] = _is_partial(m, last)
        r["income"] = r["salary_base"] + r["prime"]
        r["spent"] = r["fixed"] + r["variable"] + r["exceptional"] + r["household"] - r["reimbursement"]
        r["result"] = r["income"] + r["income_other"] - r["spent"]
        table.append(r)
    return table


def summary(table: list[dict], settings: dict, planned: list[dict], today: date) -> dict:
    full = [r for r in table if not r["partial"]][-12:]
    n = len(full) or 1
    avg = lambda k: round(sum(r[k] for r in full) / n)
    s = {k: avg(k) for k in ["salary_base", "prime", "income_other", "reimbursement", "fixed",
                              "variable", "exceptional", "household", "invest", "loisir"]}
    s["months"] = len(full)
    s["capacity_base"] = s["salary_base"] + s["reimbursement"] - s["fixed"] - s["variable"] - s["household"]
    s["capacity_smooth"] = s["capacity_base"] + s["prime"] + s["income_other"] - s["exceptional"]
    target = round(float(settings.get("epargne_cible", 300)) * 100)
    s["target"] = target
    s["loisir_room"] = s["loisir"] + s["capacity_smooth"] - target
    horizon = today + timedelta(days=365)
    planned_sum = sum(p["amount_cents"] for p in planned if today.isoformat() <= p["date"] <= horizon.isoformat())
    s["planned_sum"] = planned_sum
    s["capacity_after_planned"] = s["capacity_smooth"] + round(planned_sum / 12)
    essentials = s["fixed"] + s["variable"] + s["household"]
    livret = round(float(settings.get("livret_a_solde", 0)) * 100)
    s["livret_a"] = livret
    s["safety_months"] = round(livret / essentials, 1) if essentials else 0
    s["essentials"] = essentials
    return s
