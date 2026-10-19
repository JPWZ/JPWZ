from .categorize import categorize, kind_of, normalize_key
from .importers import IMPORTERS


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
