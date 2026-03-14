@echo off
REM Ejecutar DESPUES de las 8:00 (cuando las tablas SQL ya estan al dia).
REM Sin pause para uso en Programador de tareas (no bloquea).
cd /d "%~dp0"
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
python run_pipeline_diario.py
exit /b %ERRORLEVEL%
