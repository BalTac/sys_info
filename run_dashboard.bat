@echo off
:: Imposta la dimensione della finestra della console (110 colonne, 48 righe)
mode con: cols=110 lines=48

cd /d "%~dp0"
echo [🔄] Attivazione dell'ambiente virtuale (.venv)...
call .venv\Scripts\activate
echo [🚀] Avvio del Dashboard di Sistema (main.py)...
python main.py
pause
