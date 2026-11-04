@echo off
cd /d "%~dp0"
set TF_LOCAL_MODE=1
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto error
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1
goto end
:error
echo La configuration initiale a echoue. Verifiez Python et Internet.
pause
:end
