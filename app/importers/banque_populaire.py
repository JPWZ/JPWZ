"""Import des exports CSV Banque Populaire (compte courant)."""
import csv
import hashlib
import io
from collections import Counter
from datetime import datetime

EXPECTED = {"Date operation", "Libelle operation", "Debit", "Credit"}


def detect(header: list[str]) -> bool:
    return EXPECTED.issubset(set(header))


def _amount_cents(s: str) -> int:
    s = (s or "").replace(" ", "").replace(" ", "").replace("+", "").replace(",", ".")
    return round(float(s) * 100) if s else 0


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse(raw: bytes, account: str = "perso_bp") -> list[dict]:
    text = _decode(raw)
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not detect(reader.fieldnames or []):
        raise ValueError("Format de fichier non reconnu (export Banque Populaire attendu).")
    seen: Counter = Counter()
    out = []
    for r in reader:
        if not (r.get("Date operation") or "").strip():
            continue
        date = datetime.strptime(r["Date operation"].strip(), "%d/%m/%Y").date().isoformat()
        amount = _amount_cents(r["Debit"]) + _amount_cents(r["Credit"])
        label = r["Libelle operation"].strip()
        ref = (r.get("Reference") or "").strip()
        base = f"{account}|{ref}|{date}|{label}|{amount}"
        seen[base] += 1  # deux opérations strictement identiques le même jour restent distinctes
        out.append({
            "uid": hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest(),
            "account": account,
            "date": date,
            "label": label,
            "short": (r.get("Libelle simplifie") or "").strip(),
            "info": (r.get("Informations complementaires") or "").strip(),
            "amount_cents": amount,
            "bank_type": (r.get("Type operation") or "").strip(),
            "bank_cat": (r.get("Categorie") or "").strip(),
            "bank_sub": (r.get("Sous categorie") or "").strip(),
        })
    return out
