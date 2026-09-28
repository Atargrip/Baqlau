@echo off
chcp 65001 > nul
echo ===================================================
echo   Запуск Baqlau (Финансовый дашборд)
echo ===================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ОШИБКА] Виртуальное окружение .venv не найдено!
    pause
    exit /b
)

echo [OK] Запуск локального сервера...
echo [OK] Ссылка: http://127.0.0.1:8000/
echo [INFO] Для остановки сервера нажмите Ctrl + C в этом окне.
echo.
start http://127.0.0.1:8000/
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
pause
