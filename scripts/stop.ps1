$ErrorActionPreference = 'Stop'
$brokerRoot = Split-Path -Parent $PSScriptRoot
foreach ($brokerService in @('api', 'web')) {
    $brokerPidPath = Join-Path $brokerRoot ".runtime\$brokerService.pid"
    if (-not (Test-Path -LiteralPath $brokerPidPath)) { continue }
    $brokerProcessId = [int](Get-Content -LiteralPath $brokerPidPath)
    $brokerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$brokerProcessId"
    if ($brokerProcess) {
        $brokerNeedle = if ($brokerService -eq 'api') { 'uvicorn app.main:app' } else { 'node_modules/vite/bin/vite.js' }
        if (-not $brokerProcess.CommandLine.Contains($brokerNeedle)) {
            throw "PID $brokerProcessId no longer belongs to the recorded Helm $brokerService service; refusing to stop it."
        }
        Stop-Process -Id $brokerProcessId
    }
    Remove-Item -LiteralPath $brokerPidPath
}
Write-Output 'Stopped the recorded Helm Broker preview processes.'
