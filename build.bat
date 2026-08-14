@echo off
setlocal
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WisadelDeleter ^
  --add-data "assets;assets" ^
  --hidden-import send2trash ^
  --collect-all uiautomation ^
  main.py
if errorlevel 1 exit /b %errorlevel%
echo Built: dist\WisadelDeleter.exe
