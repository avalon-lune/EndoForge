param(
    [string]$UePackageDirectory = '',
    [string]$PhysicsRuntimeDirectory = '',
    [string]$OutputDirectory = '',
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $UePackageDirectory) { $UePackageDirectory = Join-Path $WorkspaceRoot 'Prototype/Packages/Windows' }
if (-not $PhysicsRuntimeDirectory) { $PhysicsRuntimeDirectory = Join-Path $WorkspaceRoot 'Physics/runtime' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $WorkspaceRoot ("output/Phase3/EndoForge") }
$UePackageDirectory = [System.IO.Path]::GetFullPath($UePackageDirectory)
$PhysicsRuntimeDirectory = [System.IO.Path]::GetFullPath($PhysicsRuntimeDirectory)
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
$AllowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $WorkspaceRoot ("output/Phase3"))).TrimEnd('\','/')
if (-not $OutputDirectory.StartsWith($AllowedOutputRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Distribution destination must be a child directory of $AllowedOutputRoot"
}
$PhysicsSourceNames = @('main.cpp','CMakeLists.txt','build.ps1','stage-runtime.ps1','download-dependencies.ps1','dependencies.json','dependency-hashes.json','README.md','test_network.py')
$PhysicsSourceNames += @('Phase2Model.h','Phase3Model.h','RunRegression.ps1','RunPhase3Regression.ps1','test_phase3_network.py','THIRD-PARTY-NOTICES.txt')
$UeSourceRoot = Join-Path $WorkspaceRoot 'Prototype/LapTrainer'
$SofaSourceArchive = Join-Path $WorkspaceRoot 'ThirdParty/SOFA/sofa-v26.06.00-source.zip'
$ReadmeSource = Join-Path $PSScriptRoot ("README-Phase3.md")
$RequiredFiles = @((Join-Path $UePackageDirectory 'LapTrainer.exe'), (Join-Path $PhysicsRuntimeDirectory 'LapPhysics.exe'), (Join-Path $UeSourceRoot 'LapTrainer.uproject'), $SofaSourceArchive, $ReadmeSource)
foreach ($SourceName in $PhysicsSourceNames) { $RequiredFiles += Join-Path $WorkspaceRoot ('Physics/' + $SourceName) }
foreach ($Required in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Required input is missing: $Required" }
}
foreach ($SourceDirectory in @('Config','Content','Source','Scripts')) {
    if (-not (Test-Path -LiteralPath (Join-Path $UeSourceRoot $SourceDirectory) -PathType Container)) {
        throw "UE source directory is missing: $SourceDirectory"
    }
}
# Reject junction/symlink ancestors before any recursive removal or copying.
$Ancestor = $OutputDirectory
while ($Ancestor -and $Ancestor.Length -ge $WorkspaceRoot.Length) {
    if (Test-Path -LiteralPath $Ancestor) {
        $Entry = Get-Item -LiteralPath $Ancestor -Force
        if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Distribution destination must not traverse a junction or symbolic link: $Ancestor"
        }
    }
    $Ancestor = Split-Path -Parent $Ancestor
}
if (Test-Path -LiteralPath $OutputDirectory) {
    if (@(Get-ChildItem -LiteralPath $OutputDirectory -Force).Count -gt 0) {
        if (-not $Replace) { throw "Destination is not empty: $OutputDirectory. Use -Replace to rebuild this generated distribution." }
        Write-Host ("Replacing verified generated output directory: {0}" -f $OutputDirectory)
        Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
Get-ChildItem -LiteralPath $UePackageDirectory -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $OutputDirectory -Recurse -Force }
$PhysicsDestination = Join-Path $OutputDirectory 'Physics'
New-Item -ItemType Directory -Path $PhysicsDestination -Force | Out-Null
    # Runtime delivery is an explicit allow-list. Numerical/network reports and
    # experimental probes belong only in curated Verification, never Physics.
    $RuntimeFiles = Get-ChildItem -LiteralPath $PhysicsRuntimeDirectory -File -Force | Where-Object {
        $_.Extension -in @('.exe','.dll') -or $_.Name -in @('build-info.json','runtime-manifest.txt') -or
        $_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE|AUTHORS|THIRD_PARTY_NOTICES|DEPENDENCIES)([._-]|$)'
    }
    foreach ($RuntimeFile in $RuntimeFiles) {
        Copy-Item -LiteralPath $RuntimeFile.FullName -Destination $PhysicsDestination -Force
    }
    foreach ($RuntimeSubdirectory in @('licenses','etc','share')) {
        $RuntimeSubdirectoryPath = Join-Path $PhysicsRuntimeDirectory $RuntimeSubdirectory
        if (Test-Path -LiteralPath $RuntimeSubdirectoryPath -PathType Container) {
            Copy-Item -LiteralPath $RuntimeSubdirectoryPath -Destination $PhysicsDestination -Recurse -Force
        }
    }
foreach ($ScriptName in @('StartTrainer.ps1','StartTrainer.cmd')) {
    $LauncherSource = if ($ScriptName -eq 'StartTrainer.ps1') { 'StartPhase3.ps1' } else { $ScriptName }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $LauncherSource) -Destination (Join-Path $OutputDirectory $ScriptName) -Force
}
Copy-Item -LiteralPath $ReadmeSource -Destination (Join-Path $OutputDirectory 'README.md') -Force
$LicensesDestination = Join-Path $OutputDirectory 'Licenses'
New-Item -ItemType Directory -Path $LicensesDestination -Force | Out-Null
$SofaRoot = Join-Path $WorkspaceRoot 'ThirdParty/SOFA/sdk/SOFA_v26.06.00_Win64'
foreach ($LicenseName in @('LICENSE-LGPL.md','Authors.txt','git-info.txt')) {
    $LicenseSource = Join-Path $SofaRoot $LicenseName
    if (Test-Path -LiteralPath $LicenseSource) { Copy-Item -LiteralPath $LicenseSource -Destination (Join-Path $LicensesDestination ('SOFA-' + $LicenseName)) -Force }
    else { Write-Warning "SOFA notice was not found: $LicenseSource" }
}
if (Test-Path -LiteralPath (Join-Path $SofaRoot 'licenses')) {
    Copy-Item -LiteralPath (Join-Path $SofaRoot 'licenses') -Destination (Join-Path $LicensesDestination 'SOFA-bundled-notices') -Recurse -Force
}
$BoostLicense = Join-Path $WorkspaceRoot 'ThirdParty/physics-tools/boost_1_87_0/LICENSE_1_0.txt'
if (Test-Path -LiteralPath $BoostLicense) { Copy-Item -LiteralPath $BoostLicense -Destination (Join-Path $LicensesDestination 'Boost-LICENSE_1_0.txt') -Force }
foreach ($ExtraNotice in @('THIRD_PARTY_NOTICES.md','DEPENDENCIES.md','LICENSES.md')) {
    $ExtraPath = Join-Path $WorkspaceRoot ('Physics/' + $ExtraNotice)
    if (Test-Path -LiteralPath $ExtraPath) { Copy-Item -LiteralPath $ExtraPath -Destination (Join-Path $LicensesDestination $ExtraNotice) -Force }
}
$PhysicsSourceDestination = Join-Path $OutputDirectory 'Source/Physics'
New-Item -ItemType Directory -Path $PhysicsSourceDestination -Force | Out-Null
foreach ($SourceName in $PhysicsSourceNames) {
    Copy-Item -LiteralPath (Join-Path $WorkspaceRoot ('Physics/' + $SourceName)) -Destination $PhysicsSourceDestination -Force
}
$DeliveryScriptsDestination = Join-Path $OutputDirectory 'Source/Scripts'
New-Item -ItemType Directory -Path $DeliveryScriptsDestination -Force | Out-Null
foreach ($Script in @('AssemblePhase3.ps1','RunPhase3Integration.ps1','RunPhase3Protocol.ps1','TestPhase3Package.ps1','TestPhase3Archive.ps1','StartPhase3.ps1','StartTrainer.cmd','finalize_phase3.py','README-Phase3.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $Script) -Destination $DeliveryScriptsDestination -Force
}
$DocumentationDestination = Join-Path $OutputDirectory 'Source/docs'
New-Item -ItemType Directory -Path $DocumentationDestination -Force | Out-Null
foreach ($Document in @('PHASE3.md','PROTOCOL3.md','THIRD_PARTY.md')) {
    Copy-Item -LiteralPath (Join-Path $WorkspaceRoot ('docs/' + $Document)) -Destination $DocumentationDestination -Force
}
$UeSourceDestination = Join-Path $OutputDirectory 'Source/LapTrainer'
New-Item -ItemType Directory -Path $UeSourceDestination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $UeSourceRoot 'LapTrainer.uproject') -Destination $UeSourceDestination -Force
# Explicit source allow-list excludes Binaries, Intermediate, Saved and build caches.
foreach ($SourceDirectory in @('Config','Content','Source','Scripts')) {
    Copy-Item -LiteralPath (Join-Path $UeSourceRoot $SourceDirectory) -Destination (Join-Path $UeSourceDestination $SourceDirectory) -Recurse -Force
}
$DependenciesSourceDestination = Join-Path $OutputDirectory 'Source/Dependencies'
New-Item -ItemType Directory -Path $DependenciesSourceDestination -Force | Out-Null
Copy-Item -LiteralPath $SofaSourceArchive -Destination $DependenciesSourceDestination -Force
# Tests can create Saved/Logs under a previously launched UE staging directory.
# Remove only copied transient folders, while retaining curated Verification data.
$DistributionPrefix = $OutputDirectory + [System.IO.Path]::DirectorySeparatorChar
$VerificationRoot = Join-Path $OutputDirectory 'Verification'
$VerificationPrefix = $VerificationRoot + [System.IO.Path]::DirectorySeparatorChar
$TransientDirectories = Get-ChildItem -LiteralPath $OutputDirectory -Directory -Recurse -Force |
    Where-Object { $_.Name -in @('Saved','Logs') -and -not $_.FullName.StartsWith($VerificationPrefix, [System.StringComparison]::OrdinalIgnoreCase) } |
    Sort-Object @{ Expression = { $_.FullName.Length }; Descending = $true }
foreach ($TransientDirectory in $TransientDirectories) {
    $TransientPath = [System.IO.Path]::GetFullPath($TransientDirectory.FullName)
    if (-not $TransientPath.StartsWith($DistributionPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a transient directory outside the distribution: $TransientPath"
    }
    if (($TransientDirectory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to recurse into a transient junction or symbolic link: $TransientPath"
    }
    if (Test-Path -LiteralPath $TransientPath) { Remove-Item -LiteralPath $TransientPath -Recurse -Force }
}
New-Item -ItemType Directory -Path (Join-Path $OutputDirectory 'Logs') -Force | Out-Null
# An older staged UE package can retain debug symbols despite a later -nodebuginfo
# build. Strip only copied distribution PDBs; preserve all original build symbols.
Get-ChildItem -LiteralPath $OutputDirectory -File -Recurse -Filter '*.pdb' | ForEach-Object {
    if (-not $_.FullName.StartsWith($DistributionPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a debug-symbol file outside the distribution: $($_.FullName)"
    }
    Remove-Item -LiteralPath $_.FullName -Force
}
$Manifest = Get-ChildItem -LiteralPath $OutputDirectory -File -Recurse | Sort-Object FullName | ForEach-Object {
    [PSCustomObject]@{
        path = $_.FullName.Substring($OutputDirectory.Length + 1).Replace('\','/')
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$Manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'package-manifest.json') -Encoding UTF8
Write-Host ("Distribution assembled: {0}" -f $OutputDirectory)
Write-Host 'Use StartTrainer.cmd for an interactive session; use StartTrainer.ps1 -LapPhase3Test -LapAutoExit -LapCaptureDir <directory> for Phase 3 automated verification.'
