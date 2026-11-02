param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [string]$RunName = ('phase8-packaged-' + (Get-Date -Format 'yyyyMMdd-HHmmss')),
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47371
)
$ErrorActionPreference = 'Stop'
$Workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$TestRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$TestDir = [IO.Path]::GetFullPath((Join-Path $TestRoot $RunName))
if (-not $TestDir.StartsWith($TestRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Test output must remain in output/verification.' }
if (Test-Path -LiteralPath $TestDir) { throw 'Use a fresh verification directory.' }
$PhysicsExe = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$GameExe = Join-Path $PackageRoot 'LapTrainer/Binaries/Win64/LapTrainer.exe'
$LauncherScript = Join-Path $PackageRoot 'StartTrainer.ps1'
$ReceiptFile = Join-Path $PackageRoot 'phase8-build-receipt.json'
$AssetRoot = [IO.Path]::GetFullPath((Join-Path $PackageRoot 'Assets/Phase8'))
$PhysicalAsset = Join-Path $AssetRoot 'physics-mesh.json'
$SceneAsset = Join-Path $AssetRoot 'scene.json'
foreach ($Required in @($PhysicsExe,$GameExe,$LauncherScript,$ReceiptFile,$PhysicalAsset,$SceneAsset)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing $Required" }
}
$PhysicsHash = (Get-FileHash -LiteralPath $PhysicsExe -Algorithm SHA256).Hash.ToLowerInvariant()
$GameHash = (Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant()
$Receipt = Get-Content -LiteralPath $ReceiptFile -Raw | ConvertFrom-Json
if ($Receipt.phase -ne 8 -or $Receipt.schema -ne 'endoforge.phase8.build.v1') { throw 'A Phase8 identity-bound build receipt is required.' }
$Inheritance = $Receipt.native_inheritance
$PhysicalHash = (Get-FileHash -LiteralPath $PhysicalAsset -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Inheritance.schema -ne 'endoforge.phase8.native-inheritance.v1' -or $Inheritance.phase -ne 8 -or $Inheritance.passed -ne $true -or $Inheritance.execution_phase -ne 7 -or $Inheritance.native_suite_reexecuted -ne $false -or $Inheritance.new_native_35_execution -ne $false) { throw 'The build must bind the unchanged native runtime to the accepted Phase7 qualification without claiming a new Phase8 native suite.' }
if ($Inheritance.native_binary_sha256 -ne $PhysicsHash -or $Inheritance.physical_asset_sha256 -ne $PhysicalHash) { throw 'Packaged native executable/explicit Phase8 mesh differs from native inheritance evidence.' }
$Scene = Get-Content -LiteralPath $SceneAsset -Raw | ConvertFrom-Json
if ($Scene.phase -ne 8) { throw 'Packaged anatomy scene is not Phase8.' }
if ($Receipt.physics_exe_sha256 -ne $PhysicsHash -or $Receipt.game_exe_sha256 -ne $GameHash) { throw 'The packaged binaries do not match the successful build receipt.' }
function Get-Phase8RuntimeIdentity {
    $Paths = @()
    $Paths += @(Get-ChildItem -LiteralPath $PackageRoot -File | Where-Object { $_.Extension.ToLowerInvariant() -in @('.exe','.dll') })
    foreach ($FolderName in @('Engine','LapTrainer')) {
        $Folder = Join-Path $PackageRoot $FolderName
        if (Test-Path -LiteralPath $Folder) {
            $Paths += @(Get-ChildItem -LiteralPath $Folder -Recurse -File | Where-Object {
                $_.Extension -ne '.pdb' -and ($_.FullName.Substring($Folder.Length+1) -split '[\\/]') -notcontains 'Saved' -and ($_.FullName.Substring($Folder.Length+1) -split '[\\/]') -notcontains 'Logs'
            })
        }
    }
    $NativeFolder = Join-Path $PackageRoot 'Physics'
    $Paths += @(Get-ChildItem -LiteralPath $NativeFolder -File | Where-Object {
        $_.Extension.ToLowerInvariant() -in @('.exe','.dll') -or $_.Name -in @('build-info.json','runtime-manifest.txt') -or $_.Name -match '^(LICENSE|NOTICE|COPYING|THIRD-PARTY)'
    })
    foreach ($FolderName in @('licenses','etc','share','configs','assets')) {
        $Folder = Join-Path $NativeFolder $FolderName
        if (Test-Path -LiteralPath $Folder) { $Paths += @(Get-ChildItem -LiteralPath $Folder -Recurse -File) }
    }
    $Identity = [ordered]@{}
    foreach ($Path in @($Paths | Sort-Object FullName -Unique)) {
        $Relative = $Path.FullName.Substring($PackageRoot.Length+1).Replace('\','/')
        $Identity[$Relative] = (Get-FileHash -LiteralPath $Path.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $Identity
}
function Assert-Phase8RuntimeIdentity($Identity) {
    $Expected = @($Receipt.runtime_artifacts_sha256.PSObject.Properties)
    if ($Expected.Count -eq 0 -or $Identity.Count -ne $Expected.Count) { throw 'Runtime artifact membership differs from the successful build.' }
    if (@($Expected | Where-Object Name -match '\.(pak|utoc|ucas)$').Count -eq 0) { throw 'Missing cooked content identity.' }
    foreach ($Entry in $Expected) { if ($Identity[$Entry.Name] -ne $Entry.Value) { throw "Cooked content/runtime mismatch: $($Entry.Name)" } }
    $ExpectedAssets = @($Receipt.source_asset_sha256.PSObject.Properties | Where-Object { $_.Name.StartsWith('Assets/Phase8/',[StringComparison]::OrdinalIgnoreCase) })
    $ActualAssets = @(Get-ChildItem -LiteralPath $AssetRoot -Recurse -File | Where-Object { $_.Extension.ToLowerInvariant() -notin @('.blend1','.log','.pyc') -and ($_.FullName.Substring($AssetRoot.Length+1) -split '[\\/]') -notcontains '__pycache__' })
    if ($ExpectedAssets.Count -eq 0 -or $ActualAssets.Count -ne $ExpectedAssets.Count) { throw 'Phase8 authored asset membership differs from the frozen build.' }
    foreach ($Entry in $ExpectedAssets) {
        $AssetPath = [IO.Path]::GetFullPath((Join-Path $PackageRoot $Entry.Name))
        if (-not $AssetPath.StartsWith($AssetRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $AssetPath -PathType Leaf) -or (Get-FileHash -LiteralPath $AssetPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.Value) { throw "Packaged Phase8 asset differs from frozen source: $($Entry.Name)" }
    }
    $Evidence = @($Receipt.packaged_evidence.PSObject.Properties)
    if ($Evidence.Count -eq 0) { throw 'Missing packaged native-inheritance/UE validation identities.' }
    foreach ($Entry in $Evidence) {
        $EvidencePath = [IO.Path]::GetFullPath((Join-Path $PackageRoot $Entry.Value.path))
        if (-not $EvidencePath.StartsWith($PackageRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $EvidencePath -PathType Leaf) -or (Get-FileHash -LiteralPath $EvidencePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.Value.sha256) { throw "Packaged bound evidence differs: $($Entry.Name)" }
    }
    $LaunchSources = @{'StartTrainer.ps1'='Scripts/StartPhase8.ps1';'Phase7ProcessPolicy.ps1'='Scripts/Phase7ProcessPolicy.ps1';'StartTrainer.cmd'='Scripts/StartTrainer.cmd'}
    foreach ($Destination in $LaunchSources.Keys) {
        $Frozen = $Receipt.source_asset_sha256.PSObject.Properties[$LaunchSources[$Destination]].Value
        if (-not $Frozen -or (Get-FileHash -LiteralPath (Join-Path $PackageRoot $Destination) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Frozen) { throw "Packaged launch/timing source mismatch: $Destination" }
    }
}
$RuntimeIdentity = Get-Phase8RuntimeIdentity
Assert-Phase8RuntimeIdentity $RuntimeIdentity
New-Item -ItemType Directory -Path $TestDir | Out-Null
$Started = [DateTime]::UtcNow
$LauncherArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$LauncherScript+'"'),'-LapPhase8Test','-LapAutoExit','-PhysicsPort',"$PhysicsPort",'-LapCaptureDir',('"'+$TestDir+'"'))
$Shell = (Get-Command powershell.exe -ErrorAction Stop).Source
$Launcher = Start-Process -FilePath $Shell -ArgumentList $LauncherArgs -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TestDir 'launcher.stdout.log') -RedirectStandardError (Join-Path $TestDir 'launcher.stderr.log')
$LauncherHandle = $Launcher.Handle
if (-not $Launcher.WaitForExit(1800000)) {
    & taskkill.exe /PID $Launcher.Id /T /F | Out-Null
    throw 'The owned packaged acceptance process exceeded thirty minutes.'
}
$Launcher.WaitForExit(); $Launcher.Refresh()
foreach ($Log in @(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'Logs') -File | Where-Object LastWriteTimeUtc -ge $Started)) {
    if ($Log.Name -like '*-trainer.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'unreal.log') }
    elseif ($Log.Name -like '*-physics.stdout.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'physics.stdout.log') }
    elseif ($Log.Name -like '*-physics.stderr.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'physics.stderr.log') }
    elseif ($Log.Name -like '*-physics-timer-policy.json') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'native-timer-policy.json') }
    elseif ($Log.Name -like '*-trainer-timer-policy.json') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'ue-timer-policy.json') }
}
if ($Launcher.ExitCode -ne 0) { throw "Launcher exit code $($Launcher.ExitCode); evidence is in $TestDir" }
$NativeExits = @(Select-String -LiteralPath (Join-Path $TestDir 'launcher.stdout.log') -Pattern '^PHASE8_PHYSICS_EXIT_CODE=([0-9]+)$')
if ($NativeExits.Count -ne 1 -or [int]$NativeExits[0].Matches[0].Groups[1].Value -ne 0) { throw 'Native graceful exit code zero was not proved.' }
$SessionMarkers = @(Select-String -LiteralPath (Join-Path $TestDir 'launcher.stdout.log') -Pattern '^PHASE8_SESSION_DIR=(.+)$')
if ($SessionMarkers.Count -ne 1) { throw 'Expected exactly one owned native session.' }
$NativeSession = [IO.Path]::GetFullPath($SessionMarkers[0].Matches[0].Groups[1].Value.Trim())
$SessionRoot = [IO.Path]::GetFullPath((Join-Path $PackageRoot 'Sessions'))
if (-not $NativeSession.StartsWith($SessionRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Native session is outside this package.' }
Copy-Item -LiteralPath $NativeSession -Destination (Join-Path $TestDir 'native-sessions') -Recurse
$ReportPath = Join-Path $TestDir 'phase5-input-test.json'
$Report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
$RuntimePath = Join-Path $TestDir 'phase6-runtime.json'
$InteractionPath = Join-Path $TestDir 'phase6-interaction-test.json'
foreach ($Required in @($RuntimePath,$InteractionPath)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing Phase 8 evidence: $Required" }
}
$Runtime = Get-Content -LiteralPath $RuntimePath -Raw | ConvertFrom-Json
$Interaction = Get-Content -LiteralPath $InteractionPath -Raw | ConvertFrom-Json
if ($Runtime.phase -ne 8 -or $Interaction.phase -ne 8 -or $Interaction.passed -ne $true) { throw 'Phase 8 runtime/input evidence failed.' }
$RequiredChecks = @('anatomy_assets_loaded','left_contact_grip','right_contact_grip','traction_deforms','dual_hold','dual_traction_retained','release_both','preset_releases_latched_left','recorded','replay_completed','snapshot','stereo_frames','stereo_alignment','healthy','penetration_bound')
foreach ($Name in $RequiredChecks) { if ($Report.checks.$Name -ne $true) { throw "Missing or failed assertion: $Name" } }
if ($Report.phase -ne 8 -or $Report.passed -ne $true -or @($Report.errors).Count -gt 0) { throw 'Packaged Phase 8 input exercise failed.' }
if (@($Report.checks.PSObject.Properties | Where-Object { $_.Value -ne $true }).Count) { throw 'An input check failed.' }
$Snapshots = @(Get-ChildItem -LiteralPath $TestDir -Filter '*snapshot-*.png')
if ($Snapshots.Count -lt 1) { throw 'No frozen snapshot was written.' }
$Frames = @(Get-ChildItem -LiteralPath (Join-Path $TestDir 'dataset') -Filter 'frame.json' -Recurse)
if ($Frames.Count -ne 4 -or $Report.stereo_frames -ne 4) { throw 'Exactly four internal frozen stereo alignment frames are required.' }
$ExpectedGroups = @{'left_traction'=3;'bimanual_traction'=1}
$FrameRecords = @(foreach ($Frame in $Frames) {
    $Item = Get-Content -LiteralPath $Frame.FullName -Raw | ConvertFrom-Json
    if ($Item.phase -ne 8 -or -not $ExpectedGroups.ContainsKey($Item.sequence)) { throw "Unexpected alignment frame: $($Frame.FullName)" }
    $Item
})
foreach ($Name in $ExpectedGroups.Keys) {
    $Group = @($FrameRecords | Where-Object sequence -eq $Name)
    if ($Group.Count -ne $ExpectedGroups[$Name] -or @($Group | ForEach-Object { $_.frame } | Sort-Object -Unique).Count -ne $ExpectedGroups[$Name]) { throw "Internal alignment frame membership failed: $Name" }
}
$EngineFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'unreal.log') -Pattern 'LAP_PROTOCOL Invalid','Fatal error!','Assertion failed:','Unhandled Exception:' -SimpleMatch)
$PhysicsFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'physics.stderr.log'),(Join-Path $TestDir 'physics.stdout.log') -Pattern '[ERROR]','[FATAL]','FATAL ' -SimpleMatch)
if ($EngineFaults.Count -gt 0 -or $PhysicsFaults.Count -gt 0) { throw 'Protocol or fatal runtime errors in packaged logs.' }
if ((Get-FileHash -LiteralPath $PhysicsExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PhysicsHash -or (Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $GameHash) { throw 'Binaries changed during verification.' }
$RuntimeIdentityAfter = Get-Phase8RuntimeIdentity
Assert-Phase8RuntimeIdentity $RuntimeIdentityAfter
[ordered]@{
    schema='endoforge.phase8.package-run.v1'; phase=8; passed=$true; run_kind='packaged'
    game_exit_code=$Launcher.ExitCode; native_exit_code=0; physics_exe_sha256=$PhysicsHash
    game_exe_sha256=$GameHash; package_root=$PackageRoot; tested_at_utc=$Started.ToString('o')
    runtime_artifacts_sha256=$RuntimeIdentityAfter; runtime_unchanged=$true
    duration_s=([DateTime]::UtcNow-$Started).TotalSeconds; screenshot_count=$Snapshots.Count
    native_execution_phase=7; native_suite_reexecuted=$false; new_native_35_execution=$false
    alignment_scope='Four internal rest/single-traction/dual-traction/release correspondence regressions; no research sequence deliverable or teammate ingestion gate.'
    stereo_frames=$Frames.Count; input_report_sha256=(Get-FileHash -LiteralPath $ReportPath -Algorithm SHA256).Hash.ToLowerInvariant()
    runtime_report_sha256=(Get-FileHash -LiteralPath $RuntimePath -Algorithm SHA256).Hash.ToLowerInvariant()
    interaction_report_sha256=(Get-FileHash -LiteralPath $InteractionPath -Algorithm SHA256).Hash.ToLowerInvariant()
    scope='Actual packaged Phase8 PlayerController input exercise with four internal stereo alignment frames. Native qualification is inherited from the exact accepted Phase7 runtime/physical inputs. Separate runtime, timing, geometry, asset and alignment audits remain required; this receipt is not final delivery acceptance.'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $TestDir 'phase8-packaged-run.json') -Encoding utf8
Write-Host "Packaged Phase 8 input exercise passed: $TestDir"
$Report | ConvertTo-Json -Depth 8
