param([switch]$UseDefaultDns)
$ErrorActionPreference = 'Stop'
$brokerBuildRoot = Split-Path -Parent $PSScriptRoot
$brokerComposePath = Join-Path $brokerBuildRoot 'docker-compose.yml'
$brokerArguments = @('compose', '--progress', 'plain', '-f', $brokerComposePath)
if (-not $UseDefaultDns) {
    # Resolve on Windows when Docker Desktop's upstream resolver is unreliable.
    # TLS and locked wheel hashes are still verified by the package installer.
    $brokerFilesAddress = Resolve-DnsName files.pythonhosted.org -Type A | Where-Object IPAddress | Select-Object -First 1 -ExpandProperty IPAddress
    $brokerIndexAddress = Resolve-DnsName pypi.org -Type A | Where-Object IPAddress | Select-Object -First 1 -ExpandProperty IPAddress
    if (-not $brokerFilesAddress -or -not $brokerIndexAddress) { throw 'Package hosts could not be resolved by Windows' }
    $brokerBuildDirectory = Join-Path $brokerBuildRoot '.runtime\build'
    New-Item -ItemType Directory -Force $brokerBuildDirectory | Out-Null
    $brokerOverride = Join-Path $brokerBuildDirectory 'dns.json'
    $brokerDefinition = @{context='.';extra_hosts=@("files.pythonhosted.org:$brokerFilesAddress","pypi.org:$brokerIndexAddress")}
    @{services=@{api=@{build=$brokerDefinition};worker=@{build=$brokerDefinition};'mock-core'=@{build=$brokerDefinition}}} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $brokerOverride
    $brokerArguments += @('-f', $brokerOverride)
}
$brokerArguments += 'build'
Push-Location -LiteralPath $brokerBuildRoot
try {
    & docker @brokerArguments
    if ($LASTEXITCODE) { throw 'Container build failed; the dependency cache is retained for retry' }
} finally { Pop-Location }
