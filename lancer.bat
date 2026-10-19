@echo off
rem Windows : double-clic pour demarrer l'application
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe : https://www.python.org/downloads/
  echo Pense a cocher "Add python.exe to PATH" pendant l'installation.
  pause
  exit /b 1
)
if not exist .venv %PY% -m venv .venv
call .venv\Scripts\activate
pip install -q -r requirements.txt
if not exist data mkdir data
set BUDGET_DB=data\budget.db
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
echo Application sur http://localhost:8000  (ferme cette fenetre pour arreter)
python -m uvicorn app.main:app --port 8000
pause
