@echo off
powershell -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0stop-demo.ps1"
pause
