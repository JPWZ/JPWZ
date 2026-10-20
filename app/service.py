from datetime import date, timedelta

from .categorize import categorize, kind_of, merchant_sub, normalize_key
from .importers import IMPORTERS, paypal


def import_bytes(con, raw: bytes, account: str = "perso_bp") -> tuple[int, int]:
    errors = []
    parsed = None
    for imp in IMPORTERS:
        try:
            parsed = imp.parse(raw, account)
            break
        except ValueError as e:
            errors.append(str(e))
    if parsed is None:
        raise ValueError(errors[0] if errors else "Format inconnu")
    user_rules = {r["key"]: r["category"] for r in con.execute("SELECT * FROM user_rules")}
    added = 0
    with con:
        for t in parsed:
            t["key"] = normalize_key(t["label"])
            t["category"], t["source"] = categorize(t, user_rules)
            t["kind"] = kind_of(t["category"])
            cur = con.execute(
                """INSERT OR IGNORE INTO transactions
                   (uid, account, date, label, short, info, amount_cents, bank_type, bank_cat, bank_sub,
                    key, category, kind, source)
                   VALUES (:uid,:account,:date,:label,:short,:info,:amount_cents,:bank_type,:bank_cat,:bank_sub,
                           :key,:category,:kind,:source)""", t)
            added += cur.rowcount
    return added, len(parsed)


def recategorize(con) -> int:
    """Rejoue les règles sur tout ce qui n'a pas été corrigé à la main."""
    user_rules = {r["key"]: r["category"] for r in con.execute("SELECT * FROM user_rules")}
    n = 0
    with con:
        for r in con.execute("SELECT * FROM transactions WHERE source != 'user'").fetchall():
            t = dict(r)
            cat, src = categorize(t, user_rules)
            if (cat, src) != (r["category"], r["source"]):
                con.execute("UPDATE transactions SET category=?, kind=?, source=? WHERE id=?",
                            (cat, kind_of(cat), src, r["id"]))
                n += 1
    return n


def set_category(con, tx_id: int, category: str, apply_all: bool) -> int:
    tx = con.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if tx is None:
        return 0
    with con:
        if apply_all:
            con.execute("INSERT OR REPLACE INTO user_rules(key, category) VALUES (?,?)", (tx["key"], category))
            cur = con.execute("UPDATE transactions SET category=?, kind=?, source='user_rule' "
                              "WHERE key=? AND source != 'user'", (category, kind_of(category), tx["key"]))
            con.execute("UPDATE transactions SET category=?, kind=? WHERE id=?", (category, kind_of(category), tx_id))
            return cur.rowcount
        con.execute("UPDATE transactions SET category=?, kind=?, source='user' WHERE id=?",
                    (category, kind_of(category), tx_id))
    return 1


# --- PayPal ----------------------------------------------------------------------------------

def match_events(bank: list[tuple], events: list[dict], max_before=2, max_after=12) -> dict:
    """Associe chaque prélèvement bancaire (id, date ISO, montant >0) à un événement PayPal de même
    montant, survenu 0 à 12 jours avant. Couples pris par écart de dates croissant."""
    pairs = []
    for bid, bdate, amount in bank:
        bd = date.fromisoformat(bdate)
        for i, e in enumerate(events):
            if e["amount_cents"] == amount:
                gap = (bd - date.fromisoformat(e["date"])).days
                if -max_before <= gap <= max_after:
                    pairs.append((abs(gap), bid, i))
    pairs.sort()
    used_bank, used_ev, out = set(), set(), {}
    for _, bid, i in pairs:
        if bid not in used_bank and i not in used_ev:
            used_bank.add(bid)
            used_ev.add(i)
            out[bid] = events[i]
    return out


def enrich_paypal(con) -> int:  # renvoie le nombre de prélèvements rattachés
    """Remplace « PRLV SEPA PayPal » par le commerçant réel quand l'export PayPal le permet."""
    rows = con.execute("SELECT * FROM transactions WHERE COALESCE(label_orig, label) LIKE 'PRLV SEPA PayPal%'").fetchall()
    events = [dict(r) for r in con.execute("SELECT * FROM paypal_events")]
    assign = match_events([(r["id"], r["date"], -r["amount_cents"]) for r in rows], events)
    user_rules = {r["key"]: r["category"] for r in con.execute("SELECT * FROM user_rules")}
    changed = 0
    with con:
        for r in rows:
            orig = r["label_orig"] or r["label"]
            ev = assign.get(r["id"])
            if ev:
                merchant = ev["merchant"]
                label = f"PayPal · {merchant}" + (f" ({ev['note']})" if ev["note"] else "")
                key, sub = normalize_key(f"PayPal {merchant}"), merchant_sub(merchant)
            else:
                merchant, label, key, sub = None, orig, normalize_key(orig), None
            t = dict(r) | {"label": label, "key": key, "merchant": merchant}
            if r["source"] == "user":
                cat, src = r["category"], "user"
            else:
                cat, src = categorize(t, user_rules)
            new = (label, key, merchant, orig, sub, cat, kind_of(cat), src)
            if new != (r["label"], r["key"], r["merchant"], r["label_orig"], r["sub_custom"], r["category"], r["kind"], r["source"]):
                con.execute("UPDATE transactions SET label=?, key=?, merchant=?, label_orig=?, sub_custom=?, "
                            "category=?, kind=?, source=? WHERE id=?", (*new, r["id"]))
                changed += 1
    return len(assign)


def import_paypal(con, raw: bytes) -> str:
    rows = paypal.parse(raw)
    events, pending = paypal.build_events(rows)
    with con:
        for e in events:
            con.execute("INSERT OR REPLACE INTO paypal_events(tx_id, date, amount_cents, merchant, note) VALUES (?,?,?,?,?)",
                        (e["tx_id"], e["date"].isoformat(), e["amount_cents"], e["merchant"], e["note"]))
        con.execute("DELETE FROM planned WHERE source='paypal'")
        today = date.today().isoformat()
        for p in pending:
            if p["date"].isoformat() >= today:
                con.execute("INSERT INTO planned(label, date, amount_cents, source) VALUES (?,?,?,'paypal')",
                            (f"PayPal 4x · {p['merchant']} ({p['k']}/{paypal.INSTALLMENTS})", p["date"].isoformat(),
                             -p["amount_cents"]))
    matched = enrich_paypal(con)
    return f"{len(events)} paiements PayPal lus, {matched} prélèvements bancaires rattachés à un commerçant"


def import_any(con, raw: bytes, account: str = "perso_bp") -> str:
    """Détecte le type d'export (banque ou PayPal) et l'importe."""
    first = raw[:600].decode("cp1252", errors="ignore")
    if "Numéro de transaction" in first or '"Date","Heure"' in first:
        return import_paypal(con, raw)
    added, total = import_bytes(con, raw, account)
    enrich_paypal(con)
    return f"{added} nouvelles opérations ({total} lues)"
