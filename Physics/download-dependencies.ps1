$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json
foreach ($item in $manifest.dependencies) {
    $archive = Join-Path $project $item.archive
    New-Item -ItemType Directory -Force (Split-Path -Parent $archive) | Out-Null
    if (-not (Test-Path -LiteralPath $archive)) {
        & curl.exe -L --fail --retry 3 -o $archive $item.url
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $($item.name)" }
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $item.sha256) {
        throw "SHA-256 mismatch: $archive. Preserve the file and investigate; do not automatically trust changed bytes."
    }
    if ($item.extract -and -not (Test-Path -LiteralPath (Join-Path $project $item.marker))) {
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $project $item.extract)
    }
    Write-Host "Verified $($item.name) $($item.version)"
}
