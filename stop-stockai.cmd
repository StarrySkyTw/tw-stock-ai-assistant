@echo off
title 台股 AI 投資決策助手 - 關閉
cd /d C:\stockai
echo 正在關閉台股 AI 助手...
docker compose -p stockai down
echo 已關閉。
timeout /t 2 /nobreak >nul
exit /b 0

