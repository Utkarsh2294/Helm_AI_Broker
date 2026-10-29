param([switch]$Install, [switch]$CrewAI)
$ErrorActionPreference = 'Stop'
$brokerRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $brokerRoot
if ($Install -or -not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    uv sync --frozen --extra dev --extra agents
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
if ($Install -or -not (Test-Path -LiteralPath 'apps\web\node_modules')) {
    Push-Location -LiteralPath 'apps\web'
    try { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed' } }
    finally { Pop-Location }
}
New-Item -ItemType Directory -Force '.runtime' | Out-Null
$env:PYTHONUTF8 = '1'
if ($CrewAI) { $env:HELM_AGENT_RUNTIME = 'crewai' }
& '.venv\Scripts\python.exe' -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
foreach ($brokerPort in @(8010, 5180)) {
    if (Get-NetTCPConnection -LocalPort $brokerPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $brokerPort is already in use. Stop this project's preview with scripts/stop.ps1 or choose another instance."
    }
}
$brokerApi = Start-Process -FilePath "$brokerRoot\.venv\Scripts\python.exe" `
    -ArgumentList '-m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8010' `
    -WorkingDirectory $brokerRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$brokerRoot\.runtime\api.stdout.log" -RedirectStandardError "$brokerRoot\.runtime\api.stderr.log"
$brokerApi.Id | Set-Content '.runtime\api.pid'
$brokerNode = (Get-Command node.exe).Source
$brokerWeb = Start-Process -FilePath $brokerNode `
    -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5180 --strictPort' `
    -WorkingDirectory "$brokerRoot\apps\web" -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$brokerRoot\.runtime\web.stdout.log" -RedirectStandardError "$brokerRoot\.runtime\web.stderr.log"
$brokerWeb.Id | Set-Content '.runtime\web.pid'
$brokerReady = $false
for ($brokerAttempt = 0; $brokerAttempt -lt 30; $brokerAttempt++) {
    try {
        $null = Invoke-RestMethod 'http://127.0.0.1:8010/health' -TimeoutSec 2
        $brokerReady = $true
        break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $brokerReady) { throw 'API did not become ready. Read .runtime/api.stderr.log' }
$brokerListener = Get-NetTCPConnection -LocalPort 8010 -State Listen | Select-Object -First 1
$brokerListener.OwningProcess | Set-Content '.runtime\api.pid'
Write-Output 'Helm Broker: http://127.0.0.1:5180/'
Write-Output 'Demo login: broker@helm.demo / HelmDemo!2026'
