@echo off
REM Démarrage local (hors Docker)
cd /d "%~dp0"
IF NOT EXIST .venv (
    echo Création de l'environnement virtuel...
    python -m venv .venv
    call .venv\Scripts\activate
    pip install -r requirements.txt
) ELSE (
    call .venv\Scripts\activate
)
echo.
echo 🚀  Démarrage de l'Email Campaign Manager...
echo 📧  http://localhost:5000
echo.
python app.py
