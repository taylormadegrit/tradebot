# Build a clean distributable zip for teammates.
#   powershell -ExecutionPolicy Bypass -File package.ps1
# Produces dist\tradebot-<date>.zip  (no secrets, no venv, no generated data)

$ErrorActionPreference = 'Stop'
$root    = $PSScriptRoot
$stamp   = Get-Date -Format 'yyyyMMdd'
$stage   = Join-Path $env:TEMP "tradebot-pkg-$stamp"
$distDir = Join-Path $root 'dist'
$zip     = Join-Path $distDir "tradebot-$stamp.zip"

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage   | Out-Null
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

$exDirs  = @('.venv','node_modules','dist','.pm2','__pycache__','.git')
$exFiles = @('.env','*.pyc','*.log','bot.db','bot.db-shm','bot.db-wal','HALT','I_UNDERSTAND_LIVE_RISK')

robocopy $root $stage /E /XD $exDirs /XF $exFiles /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
$global:LASTEXITCODE = 0

# empty data folder, keep the directory
$dataDir = Join-Path $stage 'data'
if (Test-Path $dataDir) { Get-ChildItem $dataDir -Force | Remove-Item -Recurse -Force }
else { New-Item -ItemType Directory $dataDir | Out-Null }
Set-Content -Path (Join-Path $dataDir '.gitkeep') -Value '' -Encoding ascii

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip
Remove-Item $stage -Recurse -Force

$mb = [math]::Round((Get-Item $zip).Length / 1MB, 2)
Write-Host "built $zip  ($mb MB)"
