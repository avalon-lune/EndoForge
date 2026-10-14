param(
    [string]$ArchivePath = '',
    [string]$RunName = ('phase3-relocated-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
$Workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$PhaseRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/Phase3'))
if (-not $ArchivePath) { $ArchivePath = Join-Path $PhaseRoot 'EndoForge_Phase3_Win64.zip' }
$ArchivePath = [IO.Path]::GetFullPath($ArchivePath)
if (-not $ArchivePath.StartsWith($PhaseRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive must be under output/Phase3.' }
$ArchiveHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$ExpectedHash = ((Get-Content -LiteralPath ($ArchivePath + '.sha256') -Raw).Trim() -split '\s+')[0]
if ($ArchiveHash -ne $ExpectedHash) { throw 'ZIP hash does not match its sidecar.' }
$VerifyRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$ExtractRoot = [IO.Path]::GetFullPath((Join-Path $VerifyRoot ($RunName + '-extracted')))
if (-not $ExtractRoot.StartsWith($VerifyRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Extraction path must remain inside output/verification.' }
if (Test-Path -LiteralPath $ExtractRoot) { throw "Use a new relocation directory: $ExtractRoot" }
$Ancestor = Split-Path -Parent $ExtractRoot
while ($Ancestor -and $Ancestor.Length -ge $Workspace.Length) {
    if (Test-Path -LiteralPath $Ancestor) {
        if (((Get-Item -LiteralPath $Ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Extraction path traverses a reparse point: $Ancestor" }
    }
    $Ancestor = Split-Path -Parent $Ancestor
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
# Validate each ZIP path before invoking framework extraction.
$Zip = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
try {
    foreach ($Entry in $Zip.Entries) {
        $Target = [IO.Path]::GetFullPath((Join-Path $ExtractRoot $Entry.FullName))
        if (-not $Target.StartsWith($ExtractRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path.' }
    }
} finally { $Zip.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath, $ExtractRoot)
$PackageRoot = Join-Path $ExtractRoot 'EndoForge'
$Manifest = @(Get-Content -LiteralPath (Join-Path $PackageRoot 'package-manifest.json') -Raw | ConvertFrom-Json)
foreach ($Entry in $Manifest) {
    $Path = [IO.Path]::GetFullPath((Join-Path $PackageRoot $Entry.path))
    if (-not $Path.StartsWith($PackageRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe manifest path.' }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing extracted file: $($Entry.path)" }
    if ((Get-Item -LiteralPath $Path).Length -ne $Entry.bytes -or (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) { throw "Extracted hash mismatch: $($Entry.path)" }
}
$FileCount = @(Get-ChildItem -LiteralPath $PackageRoot -Recurse -File).Count
if ($FileCount -ne $Manifest.Count + 1) { throw 'Extracted file count differs from manifest.' }
& (Join-Path $PSScriptRoot 'TestPhase3Package.ps1') -PackageRoot $PackageRoot -RunName $RunName
if ($ArchiveHash -ne (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'ZIP changed during relocation verification.' }
$RunReceipt = Get-Content -LiteralPath (Join-Path $VerifyRoot ($RunName + '/phase3-packaged-run.json')) -Raw | ConvertFrom-Json
if ($RunReceipt.passed -ne $true) { throw 'Relocated package did not pass.' }
[ordered]@{
    phase = 3; passed = $true; archive_sha256 = $ArchiveHash; archive_bytes = (Get-Item -LiteralPath $ArchivePath).Length
    extracted_package = $PackageRoot; verified_manifest_files = $Manifest.Count; packaged_run_directory = (Join-Path $VerifyRoot $RunName)
    physics_exe_sha256 = $RunReceipt.physics_exe_sha256; game_exe_sha256 = $RunReceipt.game_exe_sha256
    tested_at_utc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PhaseRoot 'archive-relocation-verification.json') -Encoding UTF8
Write-Host "Phase 3 ZIP relocation and packaged acceptance passed: $ExtractRoot"
