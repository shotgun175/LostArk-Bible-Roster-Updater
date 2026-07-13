@echo off
start powershell -NoExit -Command "& { Set-Location '%~dp0'; if (-not (Test-Path .\venv\Scripts\Activate.ps1)) { Write-Host 'venv not found - run: python -m venv venv (see README First-time setup)' } else { .\venv\Scripts\Activate.ps1; python main.py --help } }"
