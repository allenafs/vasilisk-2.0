@echo off
chcp 65001 >nul
title ВАСИЛИСК 2.0 — ДЕМО (без Dota 2)
cd /d "%~dp0"

python -m pip show aiohttp >nul 2>nul || python -m pip install -r requirements.txt --quiet

echo === ДЕМО ВАСИЛИСК 2.0 (ALLENAFS): тренировка без запуска Dota 2 ===
echo В отдельном окне поднимется тренер, затем симулятор пришлёт ему
echo 24-минутный матч (Рошан, БКБ, варды, Пудж-ганк, падение башни).
echo.
start "ВАСИЛИСК 2.0 server" cmd /k python src\main.py --mode console --no-voice
timeout /t 4 >nul
python tools\simulate_match.py
echo.
echo Посмотри окно "ВАСИЛИСК 2.0 server": там советы тренера и таймеры.
pause
