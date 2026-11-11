@echo off
chcp 65001 >nul
title ВАСИЛИСК 2.0 — установка всего одной кнопкой
cd /d "%~dp0"

echo.
echo  ==============================================
echo   ВАСИЛИСК 2.0 — установка всего для полного функционала
echo   создатель: ALLENAFS
echo   при поддержке: Carassius, Репозиторий Гитхабович, GLM
echo  ==============================================
echo.

rem ---------- [0] Python есть? ----------
where python >nul 2>nul
if %errorlevel%==0 goto :run

echo [0] Python не найден - устанавливаю автоматически (winget)...
where winget >nul 2>nul
if not %errorlevel%==0 (
    echo     Winget недоступен. Установи Python 3.10+ вручную:
    echo       https://www.python.org/downloads/windows/
    echo     ВАЖНО: поставь галочку "Add python.exe to PATH"!
    start https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
where python >nul 2>nul
if not %errorlevel%==0 (
    echo.
    echo     Python установлен, но PATH обновится только в новой консоли.
    echo     ЗАПУСТИ ЭТОТ ФАЙЛ ЕЩЁ РАЗ ^(двойной клик^).
    pause
    exit /b 1
)

:run
rem ---------- [1..6] всё остальное ----------
python tools\install_all.py --all

echo.
echo Готово. Запуск тренера: ярлык "ВАСИЛИСК 2.0" на рабочем столе,
echo или launcher.pyw, или start.bat
echo.
pause
