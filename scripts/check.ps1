$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps/api"
$WebDir = Join-Path $Root "apps/web"
$NativePython = Join-Path $Root ".native/api-venv/Scripts/python.exe"

function Add-PathPrefix {
  param([string]$PathToAdd)

  if (-not (Test-Path $PathToAdd)) {
    return
  }
  $parts = $env:PATH -split ";"
  if ($parts -notcontains $PathToAdd) {
    $env:PATH = "$PathToAdd;$env:PATH"
  }
}

function Get-ToolPath {
  param([string]$Name)

  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    if ($command.Path) {
      return $command.Path
    }
    return $command.Source
  }
  return $null
}

function Resolve-Python {
  if (Test-Path $NativePython) {
    return $NativePython
  }

  $python = Get-ToolPath "python"
  if ($python) {
    return $python
  }

  throw "Python was not found. Run stockai-native-app.ps1 once to create .native\api-venv, or install Python 3.12."
}

function Resolve-Pnpm {
  $codexDeps = Join-Path $HOME ".cache/codex-runtimes/codex-primary-runtime/dependencies"
  Add-PathPrefix (Join-Path $codexDeps "node/bin")
  Add-PathPrefix (Join-Path $codexDeps "bin")

  $pnpm = Get-ToolPath "pnpm"
  if ($pnpm) {
    return $pnpm
  }

  $codexPnpm = Join-Path $codexDeps "bin/pnpm.cmd"
  if (Test-Path $codexPnpm) {
    return $codexPnpm
  }

  throw "pnpm was not found. Install Node.js 22 and enable pnpm with Corepack, then rerun this check."
}

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "==> $Name"
  & $Command
}

function Assert-LastExitCode {
  param([string]$Name)

  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE."
  }
}

Invoke-Step "API tests" {
  $python = Resolve-Python
  Push-Location $ApiDir
  try {
    & $python -m pytest
    Assert-LastExitCode "API tests"
  } finally {
    Pop-Location
  }
}

Invoke-Step "Web tests" {
  $pnpm = Resolve-Pnpm
  if (-not (Get-ToolPath "node")) {
    throw "node was not found in PATH. Install Node.js 22 or use the Codex bundled runtime."
  }
  Push-Location $WebDir
  try {
    & $pnpm install --frozen-lockfile
    Assert-LastExitCode "pnpm install"
    & $pnpm test
    Assert-LastExitCode "Web tests"
    & $pnpm run build:static
    Assert-LastExitCode "Static web build"
  } finally {
    Pop-Location
  }
}
