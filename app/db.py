import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("BUDGET_DB", "data/budget.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    uid TEXT UNIQUE NOT NULL,
    account TEXT NOT NULL,
    date TEXT NOT NULL,
    label TEXT NOT NULL,
    short TEXT,
    info TEXT,
    amount_cents INTEGER NOT NULL,
    bank_type TEXT,
    bank_cat TEXT,
    bank_sub TEXT,
    key TEXT NOT NULL,
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL            -- rule | bank | user_rule | user
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_key ON transactions(key);
CREATE TABLE IF NOT EXISTS user_rules (
    key TEXT PRIMARY KEY,
    category TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS key_overrides (
    key TEXT PRIMARY KEY,
    bucket TEXT NOT NULL            -- fixed | variable
);
CREATE TABLE IF NOT EXISTS poste_flags (
    poste TEXT PRIMARY KEY,         -- "catégorie|sous-poste"
    flag TEXT NOT NULL              -- essential | discretionary
);
CREATE TABLE IF NOT EXISTS paypal_events (
    tx_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    merchant TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS planned (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL   -- negative = sortie, positif = entrée
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _migrate(con) -> None:
    """Ajoute les colonnes apparues après la première version, sans toucher aux données."""
    def add(table, column, ddl):
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    add("transactions", "merchant", "TEXT")
    add("transactions", "label_orig", "TEXT")
    add("transactions", "sub_custom", "TEXT")
    add("planned", "source", "TEXT NOT NULL DEFAULT 'manual'")
    _rename_categories(con)
    con.commit()


def _rename_categories(con) -> None:
    """Fusion de catégories : réécrit opérations, règles apprises et étiquettes essentiel/compressible."""
    from .categorize import RENAMES
    for old, new in RENAMES.items():
        con.execute("UPDATE transactions SET category=? WHERE category=?", (new, old))
        for r in con.execute("SELECT key FROM user_rules WHERE category=?", (old,)).fetchall():
            con.execute("INSERT OR REPLACE INTO user_rules(key, category) VALUES (?,?)", (r["key"], new))
        for r in con.execute("SELECT poste, flag FROM poste_flags WHERE poste LIKE ?", (old + "|%",)).fetchall():
            new_poste = new + "|" + r["poste"].split("|", 1)[1]
            con.execute("INSERT OR IGNORE INTO poste_flags(poste, flag) VALUES (?,?)", (new_poste, r["flag"]))
            con.execute("DELETE FROM poste_flags WHERE poste=?", (r["poste"],))


def get_settings(con) -> dict:
    s = {"epargne_cible": "300", "livret_a_solde": "0"}
    s.update({r["name"]: r["value"] for r in con.execute("SELECT * FROM settings")})
    return s
