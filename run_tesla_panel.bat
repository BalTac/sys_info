@echo off
:: Controlla se lo script ha i privilegi di amministratore
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run
) else (
    echo [!] Richiesta dei privilegi di amministratore...
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

:run
:: Imposta la dimensione della finestra della console (110 colonne, 48 righe)
mode con: cols=110 lines=15

:: Cambia directory nella cartella dello script
cd /d "%~dp0"

echo [🔄] Attivazione dell'ambiente virtuale (.venv)...
call .venv\Scripts\activate

echo [🚀] Avvio di main_graph.py...
python main_graph.py

echo.
echo [🛑] Script terminato. Premi un tasto per uscire.
pause
