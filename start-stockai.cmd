@echo off
title StockAI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stockai-app.ps1"
exit /b %ERRORLEVEL%
