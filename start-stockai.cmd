@echo off
title 台股 AI 投資決策助手 - 啟動
cd /d C:\stockai
echo 正在啟動 Docker Desktop 和台股 AI 助手，請稍等...

if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
)

set READY=0
for /L %%i in (1,1,60) do (
  docker info >nul 2>nul
  if not errorlevel 1 (
    set READY=1
    goto START_APP
  )
  timeout /t 2 /nobreak >nul
)

:START_APP
if "%READY%"=="0" (
  echo Docker 還沒準備好。請先手動打開 Docker Desktop，再重新點這個捷徑。
  pause
  exit /b 1
)

docker compose -p stockai up -d
if errorlevel 1 (
  echo 啟動失敗，請把這個畫面截圖給我。
  pause
  exit /b 1
)

echo 啟動完成，正在打開瀏覽器...
start "" "http://localhost:3000"
timeout /t 3 /nobreak >nul
exit /b 0

