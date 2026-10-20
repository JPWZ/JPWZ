"""Import de l'export « Activité » PayPal (CSV).

Chaque achat apparaît deux fois : le paiement au commerçant, puis une ligne « Virement bancaire sur
le compte PayPal » qui correspond au prélèvement vu sur le relevé bancaire. Les paiements en 4 fois
(« Crédit des acheteurs ») apparaissent en 4 prélèvements « PayPal Inc. » qu'on rattache à l'achat.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

FUNDING = "Virement bancaire sur le compte PayPal"
CREDIT = "Approvisionnement de paiement par Crédit des acheteurs PayPal"
INSTALLMENTS = 4
EXPECTED = {"Description", "Numéro de transaction", "Brut"}

ALIASES = {
    "apple": "Apple", "google": "Google", "airbnb": "Airbnb", "ryanair": "Ryanair", "transavia": "Transavia",
    "accor": "Accor", "booking": "Booking.com", "decathlon": "Decathlon", "zwift": "Zwift", "strava": "Strava",
    "dashlane": "Dashlane", "birkenstock": "Birkenstock", "rapha": "Rapha", "nintendo": "Nintendo",
    "kinguin": "Kinguin", "gamer2gamer": "G2G (jeux)", "21 solutions": "21 Draw", "aieu": "Alibaba",
    "big green egg": "Big Green Egg", "octobre": "Octobre Éditions", "carre blanc": "Carré Blanc",
    "secrets du chef": "Les Secrets du Chef", "lessecretsduchef": "Les Secrets du Chef", "lsdc": "Les Secrets du Chef",
}
_SUFFIX = re.compile(r"\b(s\.?a\.?s?|sas|ltd\.?|limited|b\.?v\.?|inc\.?|gmbh|llc|pte|services?)\b\.?", re.I)


def detect(header: list[str]) -> bool:
    return EXPECTED.issubset({h.strip() for h in header})


def _cents(s: str) -> int:
    s = re.sub(r"[\s  ]", "", s or "").replace(",", ".")
    return round(float(s) * 100) if s else 0


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse(raw: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(_decode(raw)))
    if not detect(reader.fieldnames or []):
        raise ValueError("Format PayPal non reconnu (export « Activité / Transactions » attendu).")
    out = []
    for r in reader:
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("Date"):
            continue
        out.append({
            "tx_id": r["Numéro de transaction"],
            "date": datetime.strptime(r["Date"], "%d/%m/%Y").date(),
            "desc": r["Description"], "currency": r.get("Devise", "EUR"), "gross": _cents(r["Brut"]),
            "name": r.get("Nom", ""), "email": r.get("Adresse email de l'expéditeur", ""),
            "ref": r.get("Numéro de la transaction de référence", ""),
        })
    return out


def clean_name(name: str, email: str = "") -> str:
    hay = f"{name} {email}".lower()
    for needle, nice in ALIASES.items():
        if needle in hay:
            return nice
    cleaned = _SUFFIX.sub("", name).strip(" .,-")
    return (cleaned or name or "Inconnu").title()


def _is_p2p(p: dict) -> bool:
    return p["desc"] == "Paiement mobile" or (p["desc"] == "Paiement standard" and p["email"] and p["name"] != "PayPal Inc.")


def build_events(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Renvoie (prélèvements bancaires attendus, échéances 4x restant à payer)."""
    by_id = {r["tx_id"]: r for r in rows}
    credits = []
    for r in rows:
        if r["desc"] == CREDIT and r["gross"] > 0 and r["ref"] in by_id:
            p = by_id[r["ref"]]
            total = r["gross"]
            credits.append({"merchant": clean_name(p["name"], p["email"]), "date": p["date"], "total": total,
                            "q": round(total / INSTALLMENTS), "dates": []})
    credits.sort(key=lambda c: c["date"])
    events = []
    funding = sorted((r for r in rows if r["desc"] == FUNDING and r["currency"] == "EUR" and r["gross"] > 0),
                     key=lambda r: r["date"])
    for f in funding:
        p = by_id.get(f["ref"])
        if p is None:
            continue
        ev = {"tx_id": f["tx_id"], "date": f["date"], "amount_cents": f["gross"], "note": "", "p2p": False}
        if p["name"] == "PayPal Inc.":
            c = next((c for c in credits if len(c["dates"]) < INSTALLMENTS and abs(f["gross"] - c["q"]) <= 3
                      and c["date"] <= f["date"] <= c["date"] + timedelta(days=125)), None)
            if c is None:
                ev["merchant"] = "Paiement en 4x (à identifier)"
            else:
                c["dates"].append(f["date"])
                ev["merchant"], ev["note"] = c["merchant"], f"échéance {len(c['dates'])}/{INSTALLMENTS}"
        elif _is_p2p(p):
            ev["merchant"], ev["p2p"] = f"Virement à {clean_name(p['name'])}", True
        else:
            ev["merchant"] = clean_name(p["name"], p["email"])
            ev["note"] = p["currency"] if p["currency"] != "EUR" else ""
        events.append(ev)
    pending = []
    for c in credits:
        done = len(c["dates"])
        for k in range(done + 1, INSTALLMENTS + 1):
            amount = c["total"] - c["q"] * (INSTALLMENTS - 1) if k == INSTALLMENTS else c["q"]
            pending.append({"merchant": c["merchant"], "k": k, "amount_cents": amount,
                            "date": c["dates"][-1] + timedelta(days=30 * (k - done))})
    return events, pending
