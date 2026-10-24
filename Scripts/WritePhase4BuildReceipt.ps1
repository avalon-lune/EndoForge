param(
    [string]$UePackageDirectory = '',
    [Parameter(Mandatory=$true)][string]$PackageLog
)
$ErrorActionPreference = 'Stop'
$Workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot 'Phase4Evidence.ps1')
if (-not $UePackageDirectory) { $UePackageDirectory = Join-Path $Workspace 'Prototype/Packages/Windows' }
$UePackageDirectory = [IO.Path]::GetFullPath($UePackageDirectory)
$GameExe = Join-Path $UePackageDirectory 'LapTrainer/Binaries/Win64/LapTrainer.exe'
$Module = Join-Path $Workspace 'Prototype/LapTrainer/Binaries/Win64/UnrealEditor-LapTrainer.dll'
$PackageLog = [IO.Path]::GetFullPath($PackageLog)
if (-not (Test-Path -LiteralPath $GameExe -PathType Leaf)) { throw 'Build the Windows package first.' }
if (-not (Select-String -LiteralPath $PackageLog -Pattern 'BUILD SUCCESSFUL' -SimpleMatch -Quiet)) { throw 'Package log does not record BUILD SUCCESSFUL.' }
$Sources = Get-Phase4SourceHashes $Workspace
[ordered]@{
    phase=4; kind='post-UAT build receipt'; created_at_utc=[DateTime]::UtcNow.ToString('o')
    game_exe_sha256=(Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant()
    editor_module_sha256=(Get-FileHash -LiteralPath $Module -Algorithm SHA256).Hash.ToLowerInvariant()
    package_log_sha256=(Get-FileHash -LiteralPath $PackageLog -Algorithm SHA256).Hash.ToLowerInvariant()
    source_files_sha256=$Sources
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $UePackageDirectory 'phase4-build-receipt.json') -Encoding UTF8
Write-Host 'Phase 4 post-UAT source and binary provenance saved.'
