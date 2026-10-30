param([switch]$Stop, [switch]$ReuseDatabase, [switch]$Postgres, [switch]$ProductionWeb, [switch]$HttpPartners)
$ErrorActionPreference = 'Stop'
$qaRoot = Split-Path -Parent $PSScriptRoot
$qaDirectory = Join-Path $qaRoot '.runtime\qa'
New-Item -ItemType Directory -Force $qaDirectory | Out-Null
if ($Stop) {
    foreach ($qaName in @('api', 'web', 'partner')) {
        $qaPidFile = Join-Path $qaDirectory "$qaName.pid"
        if (-not (Test-Path -LiteralPath $qaPidFile)) { continue }
        $qaPid = [int](Get-Content -LiteralPath $qaPidFile)
        $qaProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$qaPid"
        $qaNeedle = if ($qaName -eq 'api') { '--port 8012' } elseif ($qaName -eq 'partner') { '--port 8015' } else { '--port 5182' }
        if ($qaProcess -and $qaProcess.CommandLine.Contains($qaNeedle)) {
            foreach ($qaChild in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$qaPid")) {
                if ($qaChild.CommandLine -and $qaChild.CommandLine.Contains($qaNeedle)) { Stop-Process -Id $qaChild.ProcessId }
            }
            Stop-Process -Id $qaPid -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $qaPidFile
    }
    exit
}
$qaPython = Join-Path $env:LOCALAPPDATA 'HelmBroker\venv\Scripts\python.exe'
$qaDatabase = if ($ReuseDatabase) { (Get-ChildItem -LiteralPath $qaDirectory -Filter 'browser-*.db' | Sort-Object Name -Descending | Select-Object -First 1).FullName } else { Join-Path $qaDirectory ('browser-' + (Get-Date -Format 'yyyyMMddHHmmssfff') + '.db') }
if (-not $qaDatabase) { throw 'No QA fixture database available' }
$env:HELM_DATABASE_URL = 'sqlite:///' + $qaDatabase.Replace('\', '/')
if ($Postgres) {
    $qaDatabaseName = if ($ReuseDatabase) { & $qaPython (Join-Path $qaRoot 'tools\create_qa_database.py') --latest } else { & $qaPython (Join-Path $qaRoot 'tools\create_qa_database.py') }
    if ($LASTEXITCODE) { throw 'QA PostgreSQL database creation failed' }
    if ($qaDatabaseName -notmatch '^helm_qa_\d+$') { throw 'Unexpected QA database name' }
    $env:HELM_DATABASE_URL = "postgresql+psycopg://helm:helm_local_demo_only@127.0.0.1:55439/$qaDatabaseName"
}
$env:HELM_REDIS_URL = 'redis://127.0.0.1:56389/1'
$env:HELM_ALLOWED_ORIGIN = 'http://127.0.0.1:5182'
# QA only: shared login traffic deliberately exceeds the live five-attempt policy.
$env:HELM_AUTH_RATE_LIMIT = '500'
$env:HELM_CORE_DELIVERY_ENABLED = 'false'
$env:HELM_PARTNER_MODE = if ($HttpPartners) { 'http_simulator' } else { 'simulator' }
$env:HELM_PARTNER_SIMULATOR_URL = 'http://127.0.0.1:8015'
$env:HELM_API_PROXY = 'http://127.0.0.1:8012'
$env:PYTHONUTF8 = '1'
Push-Location -LiteralPath $qaRoot
try {
    if ($HttpPartners) {
        $qaPriorPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = Join-Path $qaRoot 'services\api'
        try { $qaPartner = Start-Process -FilePath $qaPython -ArgumentList '-m uvicorn tools.partner_sim:app --host 127.0.0.1 --port 8015' -WorkingDirectory $qaRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$qaDirectory\partner.log" -RedirectStandardError "$qaDirectory\partner.err.log" }
        finally { $env:PYTHONPATH = $qaPriorPythonPath }
        $qaPartner.Id | Set-Content "$qaDirectory\partner.pid"
    }
    & $qaPython -m alembic upgrade head
    if ($LASTEXITCODE) { throw 'QA migration failed' }
    $qaApi = Start-Process -FilePath $qaPython -ArgumentList '-m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8012' -WorkingDirectory $qaRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$qaDirectory\api.log" -RedirectStandardError "$qaDirectory\api.err.log"
    $qaWebArgs = if ($ProductionWeb) { 'server.mjs --host 127.0.0.1 --port 5182' } else { 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5182 --strictPort' }
    $qaWeb = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList $qaWebArgs -WorkingDirectory "$qaRoot\apps\web" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$qaDirectory\web.log" -RedirectStandardError "$qaDirectory\web.err.log"
    $qaApi.Id | Set-Content "$qaDirectory\api.pid"
    $qaWeb.Id | Set-Content "$qaDirectory\web.pid"
} finally { Pop-Location }
for ($qaAttempt = 0; $qaAttempt -lt 30; $qaAttempt++) {
    try { $null = Invoke-RestMethod 'http://127.0.0.1:8012/health' -TimeoutSec 2; break }
    catch { Start-Sleep -Seconds 1 }
}
if ($qaAttempt -eq 30) { throw 'QA API did not become ready' }
$qaBackendLabel = if ($Postgres) { 'PostgreSQL' } else { 'SQLite' }
Write-Output "Isolated QA: http://127.0.0.1:5182 ($qaBackendLabel fixture database and Redis DB 1)"
