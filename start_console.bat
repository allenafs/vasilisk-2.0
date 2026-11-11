@echo off
chcp 65001 >nul
title ВАСИЛИСК 2.0 — тренер (консоль)
cd /d "%~dp0"

python -m pip show aiohttp >nul 2>nul || python -m pip install -r requirements.txt --quiet

echo === ВАСИЛИСК 2.0 (ALLENAFS): консольный режим (без оверлея) ===
python src\main.py --mode console
pause
