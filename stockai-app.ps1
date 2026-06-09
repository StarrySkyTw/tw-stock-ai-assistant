$ErrorActionPreference = "Stop"

$OriginalProjectDir = $PSScriptRoot
$ProjectDir = $OriginalProjectDir
$ProjectName = "tw-stock-ai-assistant"
$Url = "http://localhost:3000"
$LogPath = Join-Path $OriginalProjectDir "stockai-app.log"
$SubstDrive = $null
$StartedCompose = $false

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

function Test-AsciiPath {
  param([string]$Path)
  foreach ($char in $Path.ToCharArray()) {
    $code = [int][char]$char
    if ($code -lt 32 -or $code -gt 126) {
      return $false
    }
  }
  return $true
}

function Get-FreeSubstDrive {
  $used = Get-PSDrive -PSProvider FileSystem | Select-Object -ExpandProperty Name
  foreach ($letter in @("S", "T", "U", "V", "W", "X", "Y", "Z", "R", "Q", "P")) {
    if ($used -notcontains $letter) {
      return "${letter}:"
    }
  }
  return $null
}

function Enable-AsciiProjectPath {
  param([string]$Path)
  if (Test-AsciiPath $Path) {
    return $Path
  }

  $drive = Get-FreeSubstDrive
  if (-not $drive) {
    throw "No free drive letter is available for Docker's ASCII-path build workaround."
  }

  Write-Log "Project path contains non-ASCII characters. Mapping $drive to $Path for Docker build."
  & subst $drive $Path
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to map $drive to $Path."
  }

  $script:SubstDrive = $drive
  return "$drive\"
}

function Disable-AsciiProjectPath {
  if ($script:SubstDrive) {
    try {
      Set-Location $OriginalProjectDir
      & subst $script:SubstDrive /D
      Write-Log "Removed temporary drive mapping $script:SubstDrive."
    } catch {
      Write-Log "Failed to remove temporary drive mapping $script:SubstDrive. $($_.Exception.Message)"
    }
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
  $ProjectDir = Enable-AsciiProjectPath $OriginalProjectDir
  Set-Location $ProjectDir
  Write-Log "Starting StockAI app launcher."

  if (Wait-Web -Seconds 4) {
    Write-Log "StockAI web is already ready. Skipping Docker Compose startup."
  } else {
    $dockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
      Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
    }

    if (-not (Wait-Docker -Seconds 120)) {
      Show-Message "Docker Desktop is not ready. Please open Docker Desktop and try again."
      exit 1
    }

    Write-Log "Starting Docker Compose services."
    docker compose -p $ProjectName up -d --build 2>&1 | Tee-Object -FilePath $LogPath -Append | Out-Host
    if ($LASTEXITCODE -ne 0) {
      if (Wait-Web -Seconds 4) {
        Write-Log "Docker Compose startup failed, but StockAI web is already ready. Continuing."
      } else {
        Show-Message "Failed to start StockAI. Please send stockai-app.log to the developer."
        exit 1
      }
    } else {
      $StartedCompose = $true
    }

    if (-not (Wait-Web -Seconds 90)) {
      Show-Message "StockAI web page did not become ready. Please send stockai-app.log to the developer."
      exit 1
    }
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

  if ($StartedCompose) {
    Write-Log "App window closed. Stopping Docker Compose services."
    docker compose -p $ProjectName down 2>&1 | Tee-Object -FilePath $LogPath -Append | Out-Host
  } else {
    Write-Log "App window closed. Existing Docker Compose services were left running."
  }
  Write-Log "StockAI stopped."
} catch {
  Write-Log $_.Exception.Message
  Show-Message "StockAI failed. Please send stockai-app.log to the developer."
  exit 1
} finally {
  Disable-AsciiProjectPath
}
