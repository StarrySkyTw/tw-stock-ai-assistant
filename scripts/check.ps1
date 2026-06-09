$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps/api"
$WebDir = Join-Path $Root "apps/web"

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "==> $Name"
  & $Command
}

Invoke-Step "API tests" {
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python was not found in PATH. Install Python 3.12 or run the API tests inside Docker."
  }
  Push-Location $ApiDir
  try {
    python -m pytest
  } finally {
    Pop-Location
  }
}

Invoke-Step "Web tests" {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found in PATH. Install Node.js 22 or run npm commands from a Node-enabled shell."
  }
  Push-Location $WebDir
  try {
    if (-not (Test-Path "node_modules")) {
      npm install
    }
    npm test
    npm run build
  } finally {
    Pop-Location
  }
}
