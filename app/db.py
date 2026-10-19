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
    return con


def get_settings(con) -> dict:
    s = {"epargne_cible": "300", "livret_a_solde": "0"}
    s.update({r["name"]: r["value"] for r in con.execute("SELECT * FROM settings")})
    return s
