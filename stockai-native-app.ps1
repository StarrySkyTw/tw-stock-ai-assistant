param(
  [switch]$SetupOnly,
  [switch]$SkipInstall,
  [switch]$NoBuild,
  [switch]$CheckRequirements,
  [switch]$SmokeTest,
  [int]$ApiPort = 18000,
  [int]$NextPort = 13000
)

$ErrorActionPreference = "Stop"

$RootDir = $PSScriptRoot
$ApiDir = Join-Path $RootDir "apps\api"
$WebDir = Join-Path $RootDir "apps\web"
$NativeDir = Join-Path $RootDir ".native"
$VenvDir = Join-Path $NativeDir "api-venv"
$ApiReadyMarker = Join-Path $VenvDir ".stockai-ready"
$LogPath = Join-Path $RootDir "stockai-native-app.log"
$ApiUrl = "http://127.0.0.1:$ApiPort"
$NextUrl = "http://127.0.0.1:$NextPort"
$ApiHealthUrl = "$ApiUrl/health"
$StaticWebDir = Join-Path $WebDir "out"

$StartedApi = $null
$StartedWeb = $null

function Write-Log {
  param([string]$Message)
  $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$time $Message" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

function Show-Message {
  param([string]$Message)
  try {
    $shell = New-Object -ComObject WScript.Shell
    $shell.Popup($Message, 0, "StockAI Native", 48) | Out-Null
  } catch {
    Write-Log $Message
  }
}

function Resolve-CommandPath {
  param([string[]]$Names)
  foreach ($name in $Names) {
    if (Test-Path $name) {
      return (Resolve-Path -LiteralPath $name).Path
    }
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }
  return $null
}

function Test-WindowsStorePythonAlias {
  param([string]$Path)
  if (-not $Path) {
    return $false
  }
  return $Path -like "*\Microsoft\WindowsApps\python*.exe"
}

function Invoke-Logged {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory
  )

  Push-Location $WorkingDirectory
  try {
    Write-Log "Running: $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments 2>&1 | ForEach-Object {
      $line = ($_ | Out-String).TrimEnd()
      if ($line) {
        Write-Log $line
      }
    }
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
  } finally {
    Pop-Location
  }
}

function Wait-HttpOk {
  param(
    [string]$TargetUrl,
    [int]$Seconds = 60
  )

  for ($i = 0; $i -lt $Seconds; $i += 2) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing $TargetUrl -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return $true
      }
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  return $false
}

function Get-PythonBootstrap {
  $localPython = Resolve-CommandPath @(
    (Join-Path $RootDir ".runtime\python\python.exe"),
    (Join-Path $RootDir "runtime\python\python.exe")
  )
  if ($localPython) {
    return @{ FilePath = $localPython; Arguments = @() }
  }

  $py = Resolve-CommandPath @("py.exe", "py")
  if ($py) {
    return @{ FilePath = $py; Arguments = @("-3.12") }
  }

  $python = Resolve-CommandPath @("python.exe", "python")
  if ($python -and -not (Test-WindowsStorePythonAlias -Path $python)) {
    return @{ FilePath = $python; Arguments = @() }
  }

  return $null
}

function Get-NpmPath {
  return Resolve-CommandPath @(
    (Join-Path $RootDir ".runtime\node\npm.cmd"),
    (Join-Path $RootDir ".runtime\nodejs\npm.cmd"),
    (Join-Path $RootDir "runtime\node\npm.cmd"),
    (Join-Path $RootDir "runtime\nodejs\npm.cmd"),
    "npm.cmd",
    "npm"
  )
}

function Test-StaticWebReady {
  return Test-Path (Join-Path $StaticWebDir "index.html")
}

function Get-NativeRequirementStatus {
  $python = Get-PythonBootstrap
  $venvPython = Join-Path $VenvDir "Scripts\python.exe"
  $venvReady = Test-Path $venvPython
  $apiDependenciesReady = Test-Path $ApiReadyMarker
  $npm = Get-NpmPath
  $nodeModules = Join-Path $WebDir "node_modules"
  $nextBuild = Join-Path $WebDir ".next"
  $staticReady = Test-StaticWebReady
  $nextReady = [bool]($npm -and (Test-Path $nodeModules) -and (Test-Path $nextBuild))
  $missing = @()

  if (-not $venvReady -and -not $python) {
    $missing += "Python 3.12 or portable .runtime\python\python.exe"
  }
  if (-not $venvReady) {
    $missing += ".native\api-venv first-run setup"
  } elseif (-not $apiDependenciesReady) {
    $missing += ".native\api-venv dependency setup marker"
  }
  if (-not $staticReady) {
    $missing += "apps\web\out static export"
    if (-not $npm) {
      $missing += "Node.js/npm 22 or portable .runtime\node\npm.cmd"
    }
    if (-not (Test-Path $nodeModules)) {
      $missing += "apps\web\node_modules first-run setup"
    }
    if (-not (Test-Path $nextBuild)) {
      $missing += "apps\web\.next production build"
    }
  }

  $launchMode = "not_ready"
  if ($venvReady -and $apiDependenciesReady -and $staticReady) {
    $launchMode = "static_fastapi"
  } elseif ($venvReady -and $apiDependenciesReady -and $nextReady) {
    $launchMode = "next_server"
  }

  $pythonPath = $null
  if ($python) {
    $pythonPath = $python.FilePath
  }

  return [ordered]@{
    root_dir = $RootDir
    launcher = "stockai-native-app.ps1"
    database = "SQLite via DATABASE_URL=sqlite:///./tw_stock_assistant.db"
    api_url = $ApiUrl
    next_url = $NextUrl
    python_bootstrap = $pythonPath
    api_venv_python = if ($venvReady) { (Resolve-Path -LiteralPath $venvPython).Path } else { $null }
    api_dependencies_ready = $apiDependenciesReady
    npm = $npm
    static_web_dir = $StaticWebDir
    static_web_ready = $staticReady
    web_node_modules_ready = Test-Path $nodeModules
    web_build_ready = Test-Path $nextBuild
    launch_mode = $launchMode
    ready_for_first_setup = [bool]($venvReady -or ($python -and ($staticReady -or $npm)))
    ready_to_launch_without_install = [bool]($venvReady -and $apiDependenciesReady -and ($staticReady -or $nextReady))
    missing = $missing
  }
}

function Ensure-ApiRuntime {
  New-Item -ItemType Directory -Force -Path $NativeDir | Out-Null
  $venvPython = Join-Path $VenvDir "Scripts\python.exe"
  $createdVenv = $false

  if (-not (Test-Path $venvPython)) {
    $python = Get-PythonBootstrap
    if (-not $python) {
      throw "Python 3.12 or compatible Python 3 was not found. Install Python or keep using Docker launcher."
    }
    Invoke-Logged -FilePath $python.FilePath -Arguments ($python.Arguments + @("-m", "venv", $VenvDir)) -WorkingDirectory $RootDir
    $createdVenv = $true
  }

  if (-not $SkipInstall -and ($createdVenv -or -not (Test-Path $ApiReadyMarker))) {
    Invoke-Logged -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -WorkingDirectory $ApiDir
    Invoke-Logged -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".") -WorkingDirectory $ApiDir
    New-Item -ItemType File -Force -Path $ApiReadyMarker | Out-Null
  }

  return $venvPython
}

function Ensure-WebAssets {
  if (Test-StaticWebReady) {
    return @{ Mode = "static"; Npm = $null; Url = $ApiUrl }
  }

  $npm = Get-NpmPath
  if (-not $npm) {
    throw "Static web export was not found and Node.js/npm is unavailable. Build apps\web\out first or keep using Docker launcher."
  }

  if (-not $SkipInstall -or -not (Test-Path (Join-Path $WebDir "node_modules"))) {
    Invoke-Logged -FilePath $npm -Arguments @("install") -WorkingDirectory $WebDir
  }

  if (-not $NoBuild -or -not (Test-StaticWebReady)) {
    $previousApiBase = $env:NEXT_PUBLIC_API_BASE_URL
    $previousOutputMode = $env:NEXT_OUTPUT_MODE
    try {
      $env:NEXT_PUBLIC_API_BASE_URL = ""
      $env:NEXT_OUTPUT_MODE = "export"
      Invoke-Logged -FilePath $npm -Arguments @("run", "build:static") -WorkingDirectory $WebDir
    } finally {
      $env:NEXT_PUBLIC_API_BASE_URL = $previousApiBase
      $env:NEXT_OUTPUT_MODE = $previousOutputMode
    }
  }

  if (Test-StaticWebReady) {
    return @{ Mode = "static"; Npm = $npm; Url = $ApiUrl }
  }

  return @{ Mode = "next"; Npm = $npm; Url = $NextUrl }
}

function Start-HiddenPowerShell {
  param(
    [string]$Name,
    [string]$WorkingDirectory,
    [string]$Command
  )

  Write-Log "Starting $Name."
  New-Item -ItemType Directory -Force -Path $NativeDir | Out-Null
  $scriptName = ($Name -replace "[^A-Za-z0-9_-]", "-").ToLowerInvariant()
  $scriptPath = Join-Path $NativeDir "$scriptName.ps1"
  $childLogPath = Join-Path $NativeDir "$scriptName.log"
  Write-Log "$Name output will be written to $childLogPath."
  $childScript = @"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
& {
$Command
} *>> '$childLogPath'
"@
  Set-Content -LiteralPath $scriptPath -Value $childScript -Encoding utf8

  return Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $scriptPath
  ) -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
}

function Stop-ProcessTree {
  param([int]$ProcessId)
  try {
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction Stop | ForEach-Object {
      Stop-ProcessTree -ProcessId $_.ProcessId
    }
  } catch {
    Write-Log "Process tree lookup failed for ${ProcessId}: $($_.Exception.Message)"
  }
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
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
  if ($CheckRequirements) {
    Get-NativeRequirementStatus | ConvertTo-Json -Depth 4
    exit 0
  }

  Write-Log "Starting StockAI native launcher."
  $venvPython = Ensure-ApiRuntime
  $webAssets = Ensure-WebAssets

  if ($SetupOnly) {
    Write-Log "SetupOnly complete."
    Show-Message "StockAI native setup is complete."
    exit 0
  }

  if (-not (Wait-HttpOk -TargetUrl $ApiHealthUrl -Seconds 2)) {
    $staticWebLine = ""
    if ($webAssets.Mode -eq "static") {
      $staticWebLine = "`$env:STATIC_WEB_DIR = '$StaticWebDir'"
    }
    $apiCommand = @"
`$env:DATABASE_URL = 'sqlite:///./tw_stock_assistant.db'
`$env:CORS_ORIGINS = '$NextUrl,http://localhost:$NextPort,http://127.0.0.1:$NextPort'
$staticWebLine
& '$venvPython' -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort
"@
    $StartedApi = Start-HiddenPowerShell -Name "native API" -WorkingDirectory $ApiDir -Command $apiCommand
  } else {
    Write-Log "API is already ready. Reusing existing process."
  }

  if (-not (Wait-HttpOk -TargetUrl $ApiHealthUrl -Seconds 60)) {
    throw "Native API did not become ready at $ApiHealthUrl."
  }

  $Url = $webAssets.Url
  if ($webAssets.Mode -eq "static") {
    if (-not (Wait-HttpOk -TargetUrl $Url -Seconds 10)) {
      throw "Native API is healthy but is not serving the static web app at $Url. Stop any existing service on port 8000 and retry."
    }
  } elseif (-not (Wait-HttpOk -TargetUrl $Url -Seconds 2)) {
    $npm = $webAssets.Npm
    $webCommand = @"
`$env:NEXT_PUBLIC_API_BASE_URL = '$ApiUrl'
& '$npm' run start -- -H 127.0.0.1 -p $NextPort
"@
    $StartedWeb = Start-HiddenPowerShell -Name "native web" -WorkingDirectory $WebDir -Command $webCommand
  } elseif ($webAssets.Mode -eq "next") {
    Write-Log "Web is already ready. Reusing existing process."
  }

  if (-not (Wait-HttpOk -TargetUrl $Url -Seconds 60)) {
    throw "Native web did not become ready at $Url."
  }

  if ($SmokeTest) {
    $analysisUrl = "$ApiUrl/api/v1/stocks/2330/analysis"
    $health = Invoke-WebRequest -UseBasicParsing $ApiHealthUrl -TimeoutSec 10
    $homeResponse = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 10
    $analysis = Invoke-WebRequest -UseBasicParsing $analysisUrl -TimeoutSec 60
    [ordered]@{
      mode = $webAssets.Mode
      api_url = $ApiUrl
      app_url = $Url
      health_status = $health.StatusCode
      app_status = $homeResponse.StatusCode
      app_content_length = $homeResponse.RawContentLength
      app_has_next_static_assets = $homeResponse.Content.Contains("/_next/static")
      analysis_status = $analysis.StatusCode
      analysis_has_research_decision = $analysis.Content.Contains("research_decision")
      static_web_ready = Test-StaticWebReady
    } | ConvertTo-Json -Depth 4
    exit 0
  }

  $edge = Find-Edge
  if (-not $edge) {
    Start-Process $Url | Out-Null
    exit 0
  }

  $profileDir = Join-Path $RootDir ".edge-native-app-profile"
  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  $arguments = @(
    "--user-data-dir=$profileDir",
    "--app=$Url",
    "--window-size=1280,900"
  )

  Write-Log "Opening Edge native app window."
  $process = Start-Process -FilePath $edge -ArgumentList $arguments -PassThru
  Wait-Process -Id $process.Id
  Write-Log "Native app window closed."
} catch {
  Write-Log "Unhandled native launcher error: $($_.Exception.Message)"
  Write-Log ($_ | Out-String)
  Show-Message "StockAI native launch failed. Please send stockai-native-app.log to the developer."
  exit 1
} finally {
  if ($StartedWeb) {
    Write-Log "Stopping native web process tree $($StartedWeb.Id)."
    Stop-ProcessTree -ProcessId $StartedWeb.Id
  }
  if ($StartedApi) {
    Write-Log "Stopping native API process tree $($StartedApi.Id)."
    Stop-ProcessTree -ProcessId $StartedApi.Id
  }
}
