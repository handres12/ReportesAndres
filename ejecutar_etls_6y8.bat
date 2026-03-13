@echo off
cd /d "%~dp0"
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
python ejecutar_etls.py
set ETL_EXIT=%ERRORLEVEL%
python push_db_to_github.py
exit /b %ETL_EXIT%
