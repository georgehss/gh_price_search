@echo off
title GH Price Search & Deal Bot
echo ====================================================
echo      INICIANDO GH PRICE SEARCH ^& DEAL BOT
echo ====================================================
echo.

if exist .venv\Scripts\python.exe (
    echo [OK] Ambiente virtual detectado (.venv)
    echo Abrindo o painel web no navegador...
    .venv\Scripts\python.exe -m streamlit run src/ui/app.py
) else (
    echo [AVISO] Executando com o Python global...
    echo Abrindo o painel web no navegador...
    python -m streamlit run src/ui/app.py
)

pause
