param([switch]$UseDefaultDns, [switch]$PrepareWheelhouse, [string]$Wheelhouse = '', [string]$BaseImage = '')
$ErrorActionPreference = 'Stop'
$brokerBuildRoot = Split-Path -Parent $PSScriptRoot
$brokerComposePath = Join-Path $brokerBuildRoot 'docker-compose.yml'
$brokerArguments = @('compose', '--progress', 'plain', '-f', $brokerComposePath)
$brokerBuildDirectory = Join-Path $env:LOCALAPPDATA 'HelmBroker\build'
New-Item -ItemType Directory -Force $brokerBuildDirectory | Out-Null
if ($PrepareWheelhouse) {
    if (-not $Wheelhouse) { $Wheelhouse = Join-Path $env:LOCALAPPDATA 'HelmBroker\linux-wheels' }
    $brokerPython = Join-Path $env:LOCALAPPDATA 'HelmBroker\venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $brokerPython)) { throw 'Run scripts/start.ps1 once to prepare the host Python environment' }
    $brokerTagImage = if ($BaseImage) { $BaseImage } else { 'python:3.12-slim' }
    $brokerTags = Join-Path $brokerBuildDirectory 'linux-tags.json'
    $brokerRequirements = Join-Path $brokerBuildDirectory 'requirements.txt'
    & docker run --rm --entrypoint python $brokerTagImage -c 'import json,platform; from pip._internal.utils.compatibility_tags import get_supported; print(json.dumps(dict(python=platform.python_version(),tags=[str(t) for t in get_supported()])))' | Set-Content -LiteralPath $brokerTags -Encoding UTF8
    if ($LASTEXITCODE) { throw 'Could not read Linux wheel compatibility tags' }
    & uv export --project $brokerBuildRoot --frozen --extra agents --extra build --no-emit-package helm-engine --no-dev --no-hashes --format requirements-txt --output-file $brokerRequirements
    if ($LASTEXITCODE) { throw 'Could not export the frozen requirements' }
    & $brokerPython (Join-Path $brokerBuildRoot 'tools\cache_linux_wheels.py') --tags $brokerTags --requirements $brokerRequirements --directory $Wheelhouse
    if ($LASTEXITCODE) { throw 'Wheel verification failed; retained downloads can be resumed' }
}
$brokerOverride = Join-Path $brokerBuildDirectory 'dns.json'
# Hydrate source bytes outside OneDrive; cloud placeholders are not valid BuildKit files.
$brokerContext = Join-Path $brokerBuildDirectory ('context-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $brokerContext | Out-Null
$brokerFiles = & git -C $brokerBuildRoot ls-files --cached --others --exclude-standard
if ($LASTEXITCODE) { throw 'Could not enumerate the project build sources' }
foreach ($brokerRelative in ($brokerFiles | Select-Object -Unique)) {
    if ($brokerRelative -notmatch '^(services/|tools/|packages/engine/|apps/web/|Dockerfile$|pyproject.toml$|uv.lock$|alembic.ini$|\.dockerignore$)') { continue }
    $brokerSource = [IO.Path]::GetFullPath((Join-Path $brokerBuildRoot $brokerRelative))
    $brokerTarget = [IO.Path]::GetFullPath((Join-Path $brokerContext $brokerRelative))
    if (-not $brokerSource.StartsWith($brokerBuildRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or -not $brokerTarget.StartsWith($brokerContext + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected build source path' }
    if (-not [IO.File]::Exists($brokerSource)) { continue }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($brokerTarget)) | Out-Null
    [IO.File]::WriteAllBytes($brokerTarget, [IO.File]::ReadAllBytes($brokerSource))
}
$brokerDefinition = @{context=$brokerContext}
if ($BaseImage) { $brokerDefinition.args = @{BASE_IMAGE=$BaseImage} }
if (-not $UseDefaultDns) {
    # Resolve on Windows when Docker Desktop's upstream resolver is unreliable.
    # TLS and locked wheel hashes are still verified by the package installer.
    $brokerFilesAddress = Resolve-DnsName files.pythonhosted.org -Type A | Where-Object IPAddress | Select-Object -First 1 -ExpandProperty IPAddress
    $brokerIndexAddress = Resolve-DnsName pypi.org -Type A | Where-Object IPAddress | Select-Object -First 1 -ExpandProperty IPAddress
    if (-not $brokerFilesAddress -or -not $brokerIndexAddress) { throw 'Package hosts could not be resolved by Windows' }
    $brokerDefinition.extra_hosts = @("files.pythonhosted.org:$brokerFilesAddress","pypi.org:$brokerIndexAddress")
}
if ($Wheelhouse) {
    $brokerWheelPath = (Resolve-Path -LiteralPath $Wheelhouse).Path
    if (-not (Get-ChildItem -LiteralPath $brokerWheelPath -Filter '*.whl' | Select-Object -First 1)) { throw 'Wheel cache is empty' }
    $brokerOfflineDockerfile = Join-Path $brokerBuildDirectory 'Dockerfile.offline'
    $brokerDockerSource = Get-Content -LiteralPath (Join-Path $brokerBuildRoot 'Dockerfile') -Raw
    $brokerDockerSource = $brokerDockerSource.Replace('    --mount=type=cache,target=/root/.cache/pip \', '    --mount=type=cache,target=/root/.cache/pip \' + [Environment]::NewLine + '    --mount=type=bind,from=wheelhouse,target=/wheelhouse \')
    $brokerDockerSource = $brokerDockerSource.Replace('--require-hashes --no-deps', '--no-index --find-links=/wheelhouse --require-hashes --no-deps')
    $brokerDockerSource | Set-Content -LiteralPath $brokerOfflineDockerfile
    $brokerDefinition.dockerfile = $brokerOfflineDockerfile
    $brokerDefinition.additional_contexts = @{wheelhouse=$brokerWheelPath}
}
if ($brokerContext) {
    @{services=@{api=@{build=$brokerDefinition};worker=@{build=$brokerDefinition};'mock-core'=@{build=$brokerDefinition};'partner-sim'=@{build=$brokerDefinition};web=@{build=@{context=(Join-Path $brokerContext 'apps/web')}}}} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $brokerOverride
    $brokerArguments += @('-f', $brokerOverride)
}
$brokerArguments += 'build'
Push-Location -LiteralPath $brokerBuildRoot
try {
    & docker @brokerArguments
    if ($LASTEXITCODE) { throw 'Container build failed; the dependency cache is retained for retry' }
} finally { Pop-Location }
