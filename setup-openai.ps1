$ErrorActionPreference = "Stop"

$ProjectDir = "C:\stockai"
$MirrorDir = "C:\Users\0628b\OneDrive\文件\股市判斷小幫手"
$ProjectDirs = @($ProjectDir, $MirrorDir) | Where-Object { Test-Path $_ }
$ProjectName = "stockai"
$TestUrl = "http://localhost:8000/api/v1/stocks/2330/analysis"

function Show-Message {
  param([string]$Message, [string]$Title = "台股 AI 助手")
  [System.Windows.Forms.MessageBox]::Show($Message, $Title, "OK", "Information") | Out-Null
}

function Get-EnvValue {
  param([string]$EnvPath, [string]$Name)
  if (-not (Test-Path $EnvPath)) { return "" }
  foreach ($line in [System.IO.File]::ReadAllLines($EnvPath, [System.Text.UTF8Encoding]::new($false))) {
    if ($line -match ("^" + [regex]::Escape($Name) + "=(.*)$")) {
      return $Matches[1]
    }
  }
  return ""
}

function Set-EnvValue {
  param([string]$EnvPath, [string]$Name, [string]$Value)
  $cleanValue = ($Value -replace "`r", "" -replace "`n", "").Trim()
  $lines = @()
  if (Test-Path $EnvPath) {
    $lines = @([System.IO.File]::ReadAllLines($EnvPath, [System.Text.UTF8Encoding]::new($false)))
  }

  $updated = New-Object System.Collections.Generic.List[string]
  $found = $false
  foreach ($line in $lines) {
    if ($line -match ("^" + [regex]::Escape($Name) + "=")) {
      $updated.Add("$Name=$cleanValue")
      $found = $true
    } else {
      $updated.Add($line)
    }
  }
  if (-not $found) {
    $updated.Add("$Name=$cleanValue")
  }

  [System.IO.File]::WriteAllLines($EnvPath, $updated.ToArray(), [System.Text.UTF8Encoding]::new($false))
}

function Wait-Docker {
  param([int]$Seconds = 120)
  for ($i = 0; $i -lt $Seconds; $i += 2) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { return $true }
    Start-Sleep -Seconds 2
  }
  return $false
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$envPath = Join-Path $ProjectDir ".env"
$currentModel = Get-EnvValue -EnvPath $envPath -Name "OPENAI_MODEL"
if ([string]::IsNullOrWhiteSpace($currentModel)) {
  $currentModel = "gpt-5.4-mini"
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "啟用 OpenAI"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(520, 300)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false

$label = New-Object System.Windows.Forms.Label
$label.Text = "請貼上你的 OpenAI API key。這個 key 只會存在本機 .env，不會顯示在畫面上。"
$label.Location = New-Object System.Drawing.Point(22, 20)
$label.Size = New-Object System.Drawing.Size(460, 42)
$form.Controls.Add($label)

$keyLabel = New-Object System.Windows.Forms.Label
$keyLabel.Text = "OpenAI API key"
$keyLabel.Location = New-Object System.Drawing.Point(22, 76)
$keyLabel.Size = New-Object System.Drawing.Size(160, 20)
$form.Controls.Add($keyLabel)

$keyBox = New-Object System.Windows.Forms.TextBox
$keyBox.Location = New-Object System.Drawing.Point(22, 100)
$keyBox.Size = New-Object System.Drawing.Size(460, 28)
$keyBox.UseSystemPasswordChar = $true
$form.Controls.Add($keyBox)

$modelLabel = New-Object System.Windows.Forms.Label
$modelLabel.Text = "模型名稱"
$modelLabel.Location = New-Object System.Drawing.Point(22, 142)
$modelLabel.Size = New-Object System.Drawing.Size(160, 20)
$form.Controls.Add($modelLabel)

$modelBox = New-Object System.Windows.Forms.TextBox
$modelBox.Location = New-Object System.Drawing.Point(22, 166)
$modelBox.Size = New-Object System.Drawing.Size(260, 28)
$modelBox.Text = $currentModel
$form.Controls.Add($modelBox)

$note = New-Object System.Windows.Forms.Label
$note.Text = "按下啟用後，系統會自動重啟後端服務。"
$note.Location = New-Object System.Drawing.Point(22, 206)
$note.Size = New-Object System.Drawing.Size(460, 22)
$form.Controls.Add($note)

$okButton = New-Object System.Windows.Forms.Button
$okButton.Text = "啟用"
$okButton.Location = New-Object System.Drawing.Point(306, 230)
$okButton.Size = New-Object System.Drawing.Size(84, 30)
$okButton.Add_Click({
  if ([string]::IsNullOrWhiteSpace($keyBox.Text)) {
    [System.Windows.Forms.MessageBox]::Show("請先貼上 OpenAI API key。", "台股 AI 助手", "OK", "Warning") | Out-Null
    return
  }
  if (-not $keyBox.Text.Trim().StartsWith("sk-")) {
    [System.Windows.Forms.MessageBox]::Show("API key 通常會以 sk- 開頭，請確認你貼的是 OpenAI API key。", "台股 AI 助手", "OK", "Warning") | Out-Null
    return
  }
  if ([string]::IsNullOrWhiteSpace($modelBox.Text)) {
    [System.Windows.Forms.MessageBox]::Show("請輸入模型名稱。", "台股 AI 助手", "OK", "Warning") | Out-Null
    return
  }
  $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $form.Close()
})
$form.Controls.Add($okButton)
$form.AcceptButton = $okButton

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "取消"
$cancelButton.Location = New-Object System.Drawing.Point(398, 230)
$cancelButton.Size = New-Object System.Drawing.Size(84, 30)
$cancelButton.Add_Click({
  $form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
  $form.Close()
})
$form.Controls.Add($cancelButton)
$form.CancelButton = $cancelButton

$result = $form.ShowDialog()
if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
  exit 0
}

foreach ($dir in $ProjectDirs) {
  $targetEnv = Join-Path $dir ".env"
  Set-EnvValue -EnvPath $targetEnv -Name "OPENAI_API_KEY" -Value $keyBox.Text
  Set-EnvValue -EnvPath $targetEnv -Name "OPENAI_MODEL" -Value $modelBox.Text
}

$dockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
if (Test-Path $dockerDesktop) {
  Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
}

if (-not (Wait-Docker -Seconds 120)) {
  Show-Message "OpenAI key 已儲存，但 Docker 尚未啟動。下次打開台股 AI 助手時會套用。"
  exit 0
}

Set-Location $ProjectDir
docker compose -p $ProjectName up -d --force-recreate api web *> $null
if ($LASTEXITCODE -ne 0) {
  Show-Message "OpenAI key 已儲存，但服務重啟失敗。請重新打開台股 AI 助手。"
  exit 1
}

Start-Sleep -Seconds 5
try {
  $analysis = Invoke-RestMethod -Uri $TestUrl -TimeoutSec 30
  if ($analysis.sentiment.model) {
    Show-Message "OpenAI 已啟用成功。現在 AI 新聞摘要會使用模型：$($analysis.sentiment.model)"
  } else {
    Show-Message "OpenAI key 已儲存，但測試時仍未成功啟用。請檢查 key 是否正確、帳戶是否有額度，或模型名稱是否可用。"
  }
} catch {
  Show-Message "OpenAI key 已儲存，但測試 API 失敗。請重新打開台股 AI 助手再試一次。"
}
