@echo off
start powershell -NoExit -Command "& { Set-Location '%~dp0'; .\venv\Scripts\Activate.ps1; python main.py --help }"
