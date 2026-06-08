$ErrorActionPreference = "Stop"

$ProjectDir = "C:\stockai"
$ProjectName = "stockai"
$Url = "http://localhost:3000"
$LogPath = Join-Path $ProjectDir "stockai-app.log"

function Write-Log {
  param([string]$Message)
  $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$time $Message" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

function Show-Message {
  param([string]$Message)
  try {
    $shell = New-Object -ComObject WScript.Shell
    $shell.Popup($Message, 0, "StockAI", 48) | Out-Null
  } catch {
    Write-Log $Message
  }
}

function Wait-Docker {
  param([int]$Seconds = 120)
  for ($i = 0; $i -lt $Seconds; $i += 2) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
      return $true
    }
    Start-Sleep -Seconds 2
  }
  return $false
}

function Wait-Web {
  param([int]$Seconds = 90)
  for ($i = 0; $i -lt $Seconds; $i += 2) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
      if ($response.StatusCode -eq 200) {
        return $true
      }
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  return $false
}

function Find-Edge {
  $candidates = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

try {
  Set-Location $ProjectDir
  Write-Log "Starting StockAI app launcher."

  $dockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  if (Test-Path $dockerDesktop) {
    Start-Process -FilePath $dockerDesktop | Out-Null
  }

  if (-not (Wait-Docker -Seconds 120)) {
    Show-Message "Docker Desktop is not ready. Please open Docker Desktop and try again."
    exit 1
  }

  Write-Log "Starting Docker Compose services."
  docker compose -p $ProjectName up -d | Out-File -FilePath $LogPath -Append -Encoding utf8
  if ($LASTEXITCODE -ne 0) {
    Show-Message "Failed to start StockAI. Please send stockai-app.log to the developer."
    exit 1
  }

  if (-not (Wait-Web -Seconds 90)) {
    Show-Message "StockAI web page did not become ready. Please send stockai-app.log to the developer."
    exit 1
  }

  $edge = Find-Edge
  if (-not $edge) {
    Start-Process $Url | Out-Null
    exit 0
  }

  $profileDir = Join-Path $ProjectDir ".edge-app-profile"
  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  $arguments = @(
    "--user-data-dir=$profileDir",
    "--app=$Url",
    "--window-size=1280,900"
  )

  Write-Log "Opening Edge app window."
  $process = Start-Process -FilePath $edge -ArgumentList $arguments -PassThru
  Wait-Process -Id $process.Id

  Write-Log "App window closed. Stopping Docker Compose services."
  docker compose -p $ProjectName down | Out-File -FilePath $LogPath -Append -Encoding utf8
  Write-Log "StockAI stopped."
} catch {
  Write-Log $_.Exception.Message
  Show-Message "StockAI failed. Please send stockai-app.log to the developer."
  exit 1
}

