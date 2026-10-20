"""Usage : python -m app.cli import chemin/vers/export.csv [--account perso_bp]"""
import argparse

from . import db
from .service import import_any, recategorize


def main():
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("path")
    imp.add_argument("--account", default="perso_bp")
    sub.add_parser("recategorize")
    args = p.parse_args()
    con = db.connect()
    if args.cmd == "import":
        with open(args.path, "rb") as f:
            print(import_any(con, f.read(), args.account))
    else:
        print(f"{recategorize(con)} opérations recatégorisées.")


if __name__ == "__main__":
    main()
