import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app import analysis, db, service
from app.categorize import categorize, normalize_key
from app.importers import banque_populaire

SAMPLE = (Path(__file__).parent / "fixtures" / "sample.csv").read_bytes()


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    return db.connect()


def txns(con):
    return [dict(r) for r in con.execute("SELECT * FROM transactions ORDER BY date, id")]


def test_parse_amounts_dates_and_encoding():
    rows = banque_populaire.parse(SAMPLE)
    salary = next(r for r in rows if r["label"] == "VIR EMPLOYEUR SA")
    assert salary["amount_cents"] == 300000 and salary["date"] == "2026-01-20"
    assert next(r for r in rows if r["label"].startswith("ECHEANCE"))["amount_cents"] == -100000
    assert any("ÉTÉ" in r["label"].upper() for r in rows)  # accents lus correctement


def test_parse_rejects_other_formats():
    with pytest.raises(ValueError):
        banque_populaire.parse(b"a;b;c\n1;2;3\n")


def test_identical_operations_same_day_are_kept_and_import_is_idempotent(con):
    added, total = service.import_bytes(con, SAMPLE)
    assert added == total
    assert service.import_bytes(con, SAMPLE)[0] == 0
    cb = [t for t in txns(con) if t["label"] == "SUPERMARCHE FR VILLE" and t["date"].startswith("2026-01")]
    assert len(cb) == 2


def test_rules(con):
    service.import_bytes(con, SAMPLE)
    by_label = {t["label"]: t for t in txns(con)}
    assert by_label["VIR EMPLOYEUR SA"]["category"] == "Autres rentrées"  # pas encore de règle générique
    assert by_label["ECHEANCE PRET"]["category"] == "Crédit immobilier"
    assert by_label["VIR SEPA COMPTE JOINT"]["kind"] == "household"
    assert by_label["VIR M JEAN-PHILIPPE WELTZER"]["kind"] == "savings_move"


def test_salary_rule_needs_min_amount():
    big = {"label": "VIR ORANGE SA", "amount_cents": 380000, "bank_cat": ""}
    small = {"label": "VIR ORANGE SA", "amount_cents": 12100, "bank_cat": ""}
    assert categorize(big)[0] == "Salaire"
    assert categorize(small)[0] == "Remboursement frais pro"


def test_user_correction_applies_to_similar_and_survives_recategorize(con):
    service.import_bytes(con, SAMPLE)
    tx = next(t for t in txns(con) if t["label"] == "SUPERMARCHE FR VILLE")
    service.set_category(con, tx["id"], "Shopping", apply_all=True)
    assert all(t["category"] == "Shopping" for t in txns(con) if t["label"] == "SUPERMARCHE FR VILLE")
    service.recategorize(con)
    assert all(t["category"] == "Shopping" for t in txns(con) if t["label"] == "SUPERMARCHE FR VILLE")


def test_normalize_key_ignores_digits():
    assert normalize_key("CARREFOUR 1234 LYON") == normalize_key("CARREFOUR 9876 LYON")


def test_recurring_detection(con):
    service.import_bytes(con, SAMPLE)
    rec = {r["label"]: r for r in analysis.detect_recurring(txns(con))}
    assert "ECHEANCE PRET" in rec and rec["ECHEANCE PRET"]["stable"]
    assert "PRLV SEPA EDF clients" in rec
    assert "CAFE" not in " ".join(rec)  # achat isolé


def test_monthly_table_splits_bonus_and_ignores_internal_moves(con):
    # on classe le salaire de test pour exercer la logique prime
    service.import_bytes(con, SAMPLE)
    con.execute("UPDATE transactions SET category='Salaire', kind='salary' WHERE label='VIR EMPLOYEUR SA'")
    con.commit()
    t = txns(con)
    table = {r["month"]: r for r in analysis.monthly_table(t, {r["key"] for r in analysis.detect_recurring(t)})}
    assert table["2026-03"]["salary_base"] == 300000 and table["2026-03"]["prime"] == 300000
    assert table["2026-01"]["prime"] == 0
    # le virement "Livret A" n'est ni une dépense ni une entrée
    assert table["2026-01"]["variable"] == 17550 and table["2026-01"]["savings_out"] == 20000
    assert table["2026-01"]["result"] == 300000 - 100000 - 10000 - 50000 - 17550


def test_summary_capacity():
    table = [{"salary_base": 300000, "prime": 0, "income_other": 0, "reimbursement": 0, "fixed": 150000,
              "variable": 100000, "exceptional": 0, "household": 50000, "invest": 0, "loisir": 0, "partial": False}] * 3
    s = analysis.summary(table, {"epargne_cible": "100"}, [], date(2026, 5, 1))
    assert s["capacity_base"] == 0 and s["loisir_room"] == -10000


def test_breakdown_matches_monthly_table_and_lists_items(con):
    service.import_bytes(con, SAMPLE)
    t = txns(con)
    keys = {r["key"] for r in analysis.detect_recurring(t)}
    months = sorted({x["date"][:7] for x in t})[:3]
    bd = analysis.breakdown(t, keys, months)
    table = {r["month"]: r for r in analysis.monthly_table(t, keys)}
    for bucket in ("fixed", "variable", "household"):
        assert bd[bucket]["total"] == sum(table[m][bucket] for m in months)
    fixed_items = [i["label"] for g in bd["fixed"]["groups"] for i in g["items"]]
    assert "ECHEANCE PRET" in fixed_items


def test_forcing_a_key_to_variable_moves_it_out_of_fixed():
    t = [{"date": f"2026-0{m}-05", "label": "ABONNEMENT X", "key": "ABONNEMENT X", "category": "Shopping",
          "kind": "expense", "amount_cents": -50000, "bank_type": "Prelevement"} for m in (1, 2, 3)]
    assert analysis.monthly_table(t, {"ABONNEMENT X"})[0]["fixed"] == 50000
    row = analysis.monthly_table(t, set(), {"ABONNEMENT X"})[0]
    assert row["fixed"] == 0 and row["variable"] == 50000 and row["exceptional"] == 0


def test_extras_rows_add_up_to_the_variable_bucket(con):
    service.import_bytes(con, SAMPLE)
    t = txns(con)
    keys = {r["key"] for r in analysis.detect_recurring(t)}
    table = {r["month"]: r for r in analysis.monthly_table(t, keys)}
    d = analysis.extras(t, keys)
    for i, m in enumerate(d["months"]):
        assert sum(r["cells"][i]["value"] for r in d["rows"]) == table[m]["variable"]
    assert analysis.default_flag("Alimentation", "Supermarché") == "essential"
    assert analysis.default_flag("Alimentation", "Restaurants") == "discretionary"


# --- PayPal -----------------------------------------------------------------------------------

from app.importers import paypal  # noqa: E402

PAYPAL = (Path(__file__).parent / "fixtures" / "paypal_sample.csv").read_bytes()


def test_paypal_events_merchants_installments_and_pending():
    events, pending = paypal.build_events(paypal.parse(PAYPAL))
    by_amount = {}
    for e in events:
        by_amount.setdefault(e["amount_cents"], []).append(e)
    assert by_amount[3000][0]["merchant"] == "Boutique Test"            # suffixe juridique retiré
    assert [e["note"] for e in by_amount[10000]] == ["échéance 1/4", "échéance 2/4"]
    assert all(e["merchant"] == "Gros Magasin" for e in by_amount[10000])
    assert by_amount[920][0]["note"] == "USD"                           # paiement en devise
    assert by_amount[102550][0]["merchant"] == "Virement à Jean Dupont"  # montant avec espace des milliers
    assert [(p["k"], p["amount_cents"]) for p in pending] == [(3, 10000), (4, 10000)]


def test_match_events_pairs_same_amounts_by_closest_date():
    events = [{"amount_cents": 199, "date": "2026-03-10", "merchant": "Apple"},
              {"amount_cents": 199, "date": "2026-03-24", "merchant": "Google"}]
    bank = [(1, "2026-03-27", 199), (2, "2026-03-12", 199), (3, "2026-05-01", 199)]
    got = service.match_events(bank, events)
    assert got[2]["merchant"] == "Apple" and got[1]["merchant"] == "Google" and 3 not in got


def test_paypal_import_relabels_bank_debits_and_categorises(con):
    bank_csv = ("Date de comptabilisation;Libelle simplifie;Libelle operation;Reference;Informations complementaires;"
                "Type operation;Categorie;Sous categorie;Debit;Credit;Date operation;Date de valeur;Pointage operation\r\n"
                + "".join(f"{d};PayPal;PRLV SEPA PayPal Europe S.a.r.l.;R{i};x;Prelevement;Shopping et services;"
                          f"Shopping et services - autre;-{a};;{d};{d};0\r\n"
                          for i, (d, a) in enumerate([("12/03/2026", "30,00"), ("14/03/2026", "100,00")]))).encode("cp1252")
    service.import_any(con, bank_csv)
    assert {t["category"] for t in txns(con)} == {"PayPal (à détailler)"}
    msg = service.import_any(con, PAYPAL)
    assert "2 prélèvements" in msg
    t = {x["merchant"]: x for x in txns(con)}
    assert t["Boutique Test"]["label"] == "PayPal · Boutique Test" and t["Boutique Test"]["label_orig"].startswith("PRLV SEPA PayPal")
    assert t["Gros Magasin"]["label"].endswith("(échéance 1/4)")
    # l'import est rejouable sans doublon ni dérive
    assert service.import_any(con, PAYPAL) and len(txns(con)) == 2
