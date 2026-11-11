@echo off
chcp 65001 >nul
title ВАСИЛИСК 2.0 — тренер (ALLENAFS)
cd /d "%~dp0"

where python >nul 2>nul || (echo Нужен Python 3.10+ — нажми: install_all.bat поставит всё сам & pause & exit /b 1)

python -m pip show aiohttp >nul 2>nul || python -m pip install -r requirements.txt --quiet

echo ==================================================
echo   ВАСИЛИСК 2.0 — ИИ-тренер по Dota 2

echo   создатель: ALLENAFS

echo   при поддержке: Carassius, Репозиторий Гитхабович, GLM
echo ==================================================
echo Голос: Windows SAPI. Оверлей поверх игры. Ctrl+C — выход.
echo Панель (вопросы ИИ, драфт, роль): http://127.0.0.1:9001/ui
echo.
python src\main.py --mode overlay
pause
