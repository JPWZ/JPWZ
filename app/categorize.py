import re
from pathlib import Path

import yaml

# catégorie -> nature de l'opération
#   salary / income_other / reimbursement / loan_in : entrées
#   expense      : dépense classique
#   household    : contribution au compte joint
#   invest       : épargne investie (PEA, crypto...)
#   savings_move : mouvement Livret A <-> compte courant (neutre)
CATEGORIES: dict[str, str] = {
    # entrées
    "Salaire": "salary",
    "Remboursement frais pro": "reimbursement",
    "Remboursement santé": "reimbursement",
    "Participation conjointe": "reimbursement",
    "Avantages CSE": "income_other",
    "Remboursement impôt": "income_other",
    "Autres rentrées": "income_other",
    "Prêt reçu": "loan_in",
    # sorties
    "Crédit immobilier": "expense",
    "Crédit conso": "expense",
    "Impôts et taxes": "expense",
    "Énergie": "expense",
    "Télécom": "expense",
    "Assurances & mutuelle": "expense",
    "Logement": "expense",
    "Frais bancaires": "expense",
    "Alimentation": "expense",
    "Transports": "expense",
    "Santé": "expense",
    "Shopping": "expense",
    "PayPal (à détailler)": "expense",
    "Loisirs & vacances": "expense",
    "Abonnements & services": "expense",
    "Juridique": "expense",
    "Famille & amis": "expense",
    "À catégoriser": "expense",
    # mouvements
    "Foyer (compte joint)": "household",
    "Investissement": "invest",
    "Livret A ⇄ courant": "savings_move",
}

LOISIR_CATEGORIES = {"Loisirs & vacances"}

# Repli sur la catégorie de la banque quand aucune règle ne correspond
BANK_MAP = {
    "banque et assurances": "Assurances & mutuelle",
    "shopping et services": "Shopping",
    "alimentation": "Alimentation",
    "logement - maison": "Logement",
    "impots et taxes": "Impôts et taxes",
    "loisirs et vacances": "Loisirs & vacances",
    "transports": "Transports",
    "sante": "Santé",
    "juridique et administratif": "Juridique",
    "revenus et rentrees d'argent": "Autres rentrées",
    "a categoriser - rentree d'argent": "Autres rentrées",
}

_RULES_PATH = Path(__file__).with_name("rules.yaml")
_rules = None


def load_rules() -> list[dict]:
    global _rules
    if _rules is None:
        raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
        _rules = []
        for r in raw:
            if r["category"] not in CATEGORIES:
                raise ValueError(f"Catégorie inconnue dans rules.yaml : {r['category']}")
            _rules.append({**r, "_re": re.compile(r["match"], re.IGNORECASE)})
    return _rules


def normalize_key(label: str) -> str:
    """Clé stable pour regrouper les opérations d'un même commerçant ou prélèvement."""
    s = re.sub(r"\d+", " ", label.upper())
    s = re.sub(r"\s+", " ", s).strip()
    return s[:28].strip()


def kind_of(category: str) -> str:
    return CATEGORIES[category]


def categorize(tx: dict, user_rules: dict[str, str] | None = None) -> tuple[str, str]:
    """Renvoie (catégorie, source)."""
    key = normalize_key(tx["label"])
    if user_rules and key in user_rules and user_rules[key] in CATEGORIES:
        return user_rules[key], "user_rule"
    amount = tx["amount_cents"]
    direction = "in" if amount > 0 else "out"
    for r in load_rules():
        if r.get("dir") and r["dir"] != direction:
            continue
        if r.get("min_eur") and abs(amount) < r["min_eur"] * 100:
            continue
        text = tx.get("merchant") if r.get("field") == "merchant" else tx["label"]
        if text and r["_re"].search(text):
            return r["category"], "rule"
    bank = BANK_MAP.get(tx.get("bank_cat", "").lower())
    if bank and (direction == "out" or kind_of(bank) != "expense"):
        return bank, "bank"
    if direction == "in":
        return "Autres rentrées", "bank"
    return "À catégoriser", "bank"


def merchant_sub(merchant: str) -> str | None:
    """Sous-poste associé à un commerçant PayPal (règles « field: merchant »)."""
    for r in load_rules():
        if r.get("field") == "merchant" and r.get("sub") and r["_re"].search(merchant):
            return r["sub"]
    return None
