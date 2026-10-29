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
        # Windows virtualenv launchers may own a second Python process.
        foreach ($brokerChild in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$brokerProcessId")) {
            if ($brokerChild.CommandLine -and $brokerChild.CommandLine.Contains($brokerNeedle)) {
                Stop-Process -Id $brokerChild.ProcessId -ErrorAction SilentlyContinue
            }
        }
        Stop-Process -Id $brokerProcessId -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $brokerPidPath
}
Write-Output 'Stopped the recorded Helm Broker preview processes.'
