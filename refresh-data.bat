@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
set "PAGES=%~1"
if "%PAGES%"=="" set "PAGES=50"

echo [1/2] Скрапинг cars.av.by (%PAGES% стр.) ...
"%PY%" -m scraper.cli --pages %PAGES%
if errorlevel 1 goto error

echo.
echo [2/2] Пересборка docs/ ...
"%PY%" "%ROOT%scripts\build-static.py"
if errorlevel 1 goto error

echo.
echo Готово: свежий срез лежит в data\cars.json
echo Дальше: на github.com откройте папку data и нажмите Add file - Upload files.
start "" explorer /select,"%ROOT%data\cars.json"
pause
exit /b 0

:error
echo.
echo Ошибка - смотрите вывод выше.
pause
exit /b 1
