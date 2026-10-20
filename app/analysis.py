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


def salary_base(txns: list[dict]) -> int:
    salaries = [t["amount_cents"] for t in txns if t["kind"] == "salary" and t["amount_cents"] > 0]
    return int(statistics.median(salaries)) if salaries else 0


def classify(t: dict, base: int, recurring_keys, force_variable=frozenset()) -> list[tuple[str, int]]:
    """Range une opération dans un ou deux postes (montants positifs, sauf rentrées)."""
    a, kind = t["amount_cents"], t["kind"]
    if kind == "salary":
        if base and a > PRIME_FACTOR * base:
            return [("salary_base", base), ("prime", a - base)]
        return [("salary_base", a)]
    if kind in ("income_other", "reimbursement", "loan_in"):
        return [(kind, a)]
    if kind == "household":
        return [("household", -a)]
    if kind == "invest":
        return [("invest", -a)]
    if kind == "savings_move":
        return [("savings_in" if a > 0 else "savings_out", abs(a))]
    if t["key"] in recurring_keys:
        return [("fixed", -a)]
    if t["key"] not in force_variable and a <= -EXCEPTIONAL_CENTS:
        return [("exceptional", -a)]
    return [("variable", -a)]


BUCKETS = ["salary_base", "prime", "income_other", "reimbursement", "loan_in", "fixed", "variable",
           "exceptional", "household", "invest", "savings_in", "savings_out"]


def monthly_table(txns: list[dict], recurring_keys, force_variable=frozenset()) -> list[dict]:
    if not txns:
        return []
    last = date.fromisoformat(max(t["date"] for t in txns))
    base = salary_base(txns)
    rows: dict[str, dict] = {}
    for t in txns:
        m = _month(t["date"])
        r = rows.setdefault(m, {k: 0 for k in BUCKETS + ["loisir"]} | {"month": m})
        for bucket, amount in classify(t, base, recurring_keys, force_variable):
            r[bucket] += amount
        if t["kind"] == "expense" and t["category"] in LOISIR_CATEGORIES:
            r["loisir"] -= t["amount_cents"]
    table = []
    for m in sorted(rows):
        r = rows[m]
        r["partial"] = _is_partial(m, last)
        r["income"] = r["salary_base"] + r["prime"]
        r["spent"] = r["fixed"] + r["variable"] + r["exceptional"] + r["household"] - r["reimbursement"]
        r["result"] = r["income"] + r["income_other"] - r["spent"]
        table.append(r)
    return table


def breakdown(txns: list[dict], recurring_keys, months: list[str], force_variable=frozenset(),
              overrides: dict | None = None, per_category: int = 14) -> dict:
    """Pour chaque poste : catégories, puis commerçants/prélèvements qui le composent."""
    overrides = overrides or {}
    base = salary_base(txns)
    wanted = set(months)
    raw: dict[str, dict[str, dict[str, dict]]] = {b: defaultdict(dict) for b in BUCKETS}
    for t in txns:
        if _month(t["date"]) not in wanted:
            continue
        for bucket, amount in classify(t, base, recurring_keys, force_variable):
            label = "Part variable du salaire (primes)" if bucket == "prime" else t["label"]
            key = t["key"] if bucket != "prime" else "PRIME"
            it = raw[bucket][t["category"]].setdefault(key, {"key": key, "label": label, "total": 0, "count": 0})
            it["total"] += amount
            it["count"] += 1
            it["label"] = label
    out = {}
    for bucket, cats in raw.items():
        groups = []
        for cat, items in cats.items():
            lst = sorted(items.values(), key=lambda i: -abs(i["total"]))
            for i in lst:
                i["override"] = overrides.get(i["key"])
            head, tail = lst[:per_category], lst[per_category:]
            if tail:
                head.append({"key": None, "label": f"Autres ({len(tail)} lignes)", "override": None,
                             "total": sum(i["total"] for i in tail), "count": sum(i["count"] for i in tail)})
            groups.append({"category": cat, "total": sum(i["total"] for i in lst),
                           "count": sum(i["count"] for i in lst), "items": head})
        groups.sort(key=lambda g: -abs(g["total"]))
        out[bucket] = {"total": sum(g["total"] for g in groups), "groups": groups}
    return out


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


# --- Vue "Où couper" : dépenses hors charges fixes, poste par poste -------------------------------

SUB_LABELS = {
    "Hyper/supermarche": "Supermarché", "Alimentation - autre": "Alimentation (autre)",
    "Petit commercant": "Petits commerçants", "Restaurant": "Restaurants",
    "Restauration rapide": "Restauration rapide", "Carburant": "Carburant",
    "Peage et Stationnement": "Péage et parking", "Transports en commun": "Transports en commun",
    "Taxis et VTC": "Taxis et VTC", "Trains, avions et ferrys": "Trains et avions",
    "Location de voiture et moto": "Location voiture/moto", "Entretien de vehicule": "Entretien véhicule",
    "Vetements et chaussures": "Vêtements et chaussures", "High-Tech/Electromenager": "High-tech / électroménager",
    "Coiffeurs et soins du corps": "Coiffeur et soins", "Shopping et services - autre": "Shopping (autre)",
    "Livres, Magazines": "Livres, magazines", "Sport, Gym et Equipement": "Sport et équipement",
    "Expo, musee, cinema": "Expos, musées, cinéma", "Video, Musique et jeux": "Vidéo, musique, jeux",
    "Bar": "Bars", "Hotel": "Hôtels", "Loisirs et vacances - autre": "Loisirs (autre)",
    "Consultation medicale": "Consultations médicales", "Pharmacie": "Pharmacie",
    "Travaux - Entretien": "Travaux et entretien", "Ameublement et appareil": "Ameublement",
    "Virement emis - a categoriser": "Virements à des proches", "Retrait d'especes - a categoriser": "Retraits d'espèces",
    "Cheque - a categoriser": "Chèques",
}
WHOLE_CATEGORY = {"PayPal (à détailler)", "Famille & amis", "Juridique", "À catégoriser", "Frais bancaires",
                   "Assurances & mutuelle", "Impôts et taxes", "Énergie", "Télécom", "Crédit conso", "Crédit immobilier"}
ESSENTIAL_LABELS = {"Supermarché", "Alimentation (autre)", "Petits commerçants", "Carburant", "Péage et parking",
                    "Transports en commun", "Entretien véhicule", "Pharmacie", "Consultations médicales",
                    "Travaux et entretien", "Ameublement"}
ESSENTIAL_CATEGORIES = {"Santé", "Logement", "Juridique", "Impôts et taxes", "Énergie", "Assurances & mutuelle",
                        "Télécom", "Frais bancaires", "Crédit conso", "Crédit immobilier"}


def poste_of(t: dict) -> tuple[str, str]:
    cat = t["category"]
    sub = t.get("sub_custom") or t.get("bank_sub")
    if cat in WHOLE_CATEGORY or not sub:
        return cat, cat
    return cat, SUB_LABELS.get(sub, sub)


def default_flag(category: str, label: str) -> str:
    if category in ESSENTIAL_CATEGORIES or label in ESSENTIAL_LABELS:
        return "essential"
    return "discretionary"


def extras(txns: list[dict], recurring_keys, force_variable=frozenset(), flag_overrides: dict | None = None,
           selected: str | None = None) -> dict:
    flag_overrides = flag_overrides or {}
    if not txns:
        return {"months": []}
    last = date.fromisoformat(max(t["date"] for t in txns))
    base = salary_base(txns)
    all_months = sorted({_month(t["date"]) for t in txns})
    months = all_months[-13:]
    complete = [m for m in months if not _is_partial(m, last)]
    selected = selected if selected in months else (complete[-1] if complete else months[-1])
    n_c = len(complete) or 1
    rows: dict[tuple, dict] = {}
    exceptional, month_ops = [], []
    for t in txns:
        m = _month(t["date"])
        if m not in months:
            continue
        for bucket, amount in classify(t, base, recurring_keys, force_variable):
            if bucket == "variable":
                cat, label = poste_of(t)
                r = rows.setdefault((cat, label), {"category": cat, "label": label, "sub_raw": t.get("sub_custom") or t.get("bank_sub", ""),
                                                    "by_month": defaultdict(int)})
                r["by_month"][m] += amount
                if m == selected:
                    month_ops.append({"date": t["date"], "label": t["label"], "key": t["key"],
                                      "poste": f"{cat} › {label}", "amount": amount, "id": t["id"]})
            elif bucket == "exceptional":
                exceptional.append({"month": m, "date": t["date"], "label": t["label"], "category": t["category"],
                                    "amount": amount, "id": t["id"]})
    out_rows = []
    for (cat, label), r in rows.items():
        poste = f"{cat}|{label}"
        flag = flag_overrides.get(poste) or default_flag(cat, label)
        total_c = sum(r["by_month"].get(m, 0) for m in complete)
        avg = total_c / n_c
        cells = []
        for m in months:
            v = r["by_month"].get(m, 0)
            ratio = v / avg if avg > 0 else (2 if v else 0)
            level = 0 if v == 0 else 3 if ratio >= 2 else 2 if ratio >= 1.4 else 1 if ratio >= 0.7 else 0
            cells.append({"month": m, "value": v, "level": level})
        sel = r["by_month"].get(selected, 0)
        out_rows.append({"poste": poste, "category": cat, "label": label, "sub_raw": r["sub_raw"], "flag": flag,
                         "overridden": poste in flag_overrides, "cells": cells, "avg": round(avg),
                         "selected": sel, "delta": sel - round(avg)})
    out_rows.sort(key=lambda r: (-sum(c["value"] for c in r["cells"] if c["month"] in complete) / n_c))
    month_totals = []
    for i, m in enumerate(months):
        ess = sum(r["cells"][i]["value"] for r in out_rows if r["flag"] == "essential")
        dis = sum(r["cells"][i]["value"] for r in out_rows if r["flag"] == "discretionary")
        exc = sum(e["amount"] for e in exceptional if e["month"] == m)
        month_totals.append({"month": m, "essential": ess, "discretionary": dis, "exceptional": exc,
                             "partial": m not in complete})
    avg_of = lambda k: round(sum(t[k] for t in month_totals if not t["partial"]) / n_c)
    s = {"essential": avg_of("essential"), "discretionary": avg_of("discretionary"), "exceptional": avg_of("exceptional")}
    s["total"] = s["essential"] + s["discretionary"]
    s["savings"] = {pct: round(s["discretionary"] * pct / 100) for pct in (10, 20, 30)}
    top_ops = sorted(month_ops, key=lambda o: -o["amount"])[:12]
    merchants: dict[str, dict] = {}
    for o in month_ops:
        g = merchants.setdefault(o["key"], {"key": o["key"], "label": o["label"], "total": 0, "count": 0})
        g["total"] += o["amount"]
        g["count"] += 1
    top_merchants = sorted(merchants.values(), key=lambda g: -g["total"])[:10]
    sel_tot = next(t for t in month_totals if t["month"] == selected)
    return {"months": months, "complete": complete, "selected": selected, "rows": out_rows,
            "month_totals": month_totals, "summary": s, "top_ops": top_ops, "top_merchants": top_merchants,
            "exceptional": sorted(exceptional, key=lambda e: e["date"], reverse=True),
            "selected_total": sel_tot["essential"] + sel_tot["discretionary"],
            "max_total": max((t["essential"] + t["discretionary"] + t["exceptional"] for t in month_totals), default=1) or 1}
