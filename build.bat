@echo off
setlocal
pushd "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo ERROR: Virtual environment not found: %PYTHON%
  echo Run: python -m venv .venv
  popd
  exit /b 1
)

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
  popd
  exit /b 1
)

"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WisadelDeleter ^
  --add-data "assets;assets" ^
  --hidden-import send2trash ^
  --collect-all uiautomation ^
  main.py
if errorlevel 1 (
  popd
  exit /b 1
)
echo Built: dist\WisadelDeleter.exe
popd
