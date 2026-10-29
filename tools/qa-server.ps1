param([switch]$Stop)
$ErrorActionPreference = 'Stop'
$qaRoot = Split-Path -Parent $PSScriptRoot
$qaDirectory = Join-Path $qaRoot '.runtime\qa'
New-Item -ItemType Directory -Force $qaDirectory | Out-Null
if ($Stop) {
    foreach ($qaName in @('api', 'web')) {
        $qaPidFile = Join-Path $qaDirectory "$qaName.pid"
        if (-not (Test-Path -LiteralPath $qaPidFile)) { continue }
        $qaPid = [int](Get-Content -LiteralPath $qaPidFile)
        $qaProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$qaPid"
        $qaNeedle = if ($qaName -eq 'api') { '--port 8012' } else { '--port 5182' }
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
$env:HELM_DATABASE_URL = 'sqlite:///' + (Join-Path $qaDirectory ('browser-' + (Get-Date -Format 'yyyyMMddHHmmssfff') + '.db')).Replace('\', '/')
$env:HELM_REDIS_URL = 'redis://127.0.0.1:56389/1'
$env:HELM_ALLOWED_ORIGIN = 'http://127.0.0.1:5182'
# QA only: shared login traffic deliberately exceeds the live five-attempt policy.
$env:HELM_AUTH_RATE_LIMIT = '500'
$env:HELM_CORE_DELIVERY_ENABLED = 'false'
$env:HELM_API_PROXY = 'http://127.0.0.1:8012'
$env:PYTHONUTF8 = '1'
Push-Location -LiteralPath $qaRoot
try {
    & $qaPython -m alembic upgrade head
    if ($LASTEXITCODE) { throw 'QA migration failed' }
    $qaApi = Start-Process -FilePath $qaPython -ArgumentList '-m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8012' -WorkingDirectory $qaRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$qaDirectory\api.log" -RedirectStandardError "$qaDirectory\api.err.log"
    $qaWeb = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5182 --strictPort' -WorkingDirectory "$qaRoot\apps\web" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$qaDirectory\web.log" -RedirectStandardError "$qaDirectory\web.err.log"
    $qaApi.Id | Set-Content "$qaDirectory\api.pid"
    $qaWeb.Id | Set-Content "$qaDirectory\web.pid"
} finally { Pop-Location }
Write-Output 'Isolated QA: http://127.0.0.1:5182 (SQLite fixture database and Redis DB 1)'
