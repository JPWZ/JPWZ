#!/bin/bash
# Mac / Linux : double-clic (ou ./lancer.command) pour démarrer l'application
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "Python 3 n'est pas installé : https://www.python.org/downloads/"; read -r -p "Entrée pour fermer"; exit 1
fi
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
mkdir -p data
export BUDGET_DB=data/budget.db
(sleep 3; (open http://localhost:8000 || xdg-open http://localhost:8000) >/dev/null 2>&1) &
echo "Application sur http://localhost:8000  (Ctrl+C pour arrêter)"
python -m uvicorn app.main:app --port 8000
