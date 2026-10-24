param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [string]$RunName = ('phase5-packaged-' + (Get-Date -Format 'yyyyMMdd-HHmmss')),
    [int]$PhysicsPort = 47327
)
$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$TestRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$TestDir = [IO.Path]::GetFullPath((Join-Path $TestRoot $RunName))
if (-not $TestDir.StartsWith($TestRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Test output must remain in output/verification.' }
if (Test-Path -LiteralPath $TestDir) { throw 'Use a fresh verification directory.' }
$PhysicsExe = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$GameExe = Join-Path $PackageRoot 'LapTrainer/Binaries/Win64/LapTrainer.exe'
$LauncherScript = Join-Path $PackageRoot 'StartTrainer.ps1'
$ReceiptFile = Join-Path $PackageRoot 'phase5-build-receipt.json'
foreach ($Required in @($PhysicsExe,$GameExe,$LauncherScript,$ReceiptFile)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing $Required" }
}
$PhysicsHash = (Get-FileHash -LiteralPath $PhysicsExe -Algorithm SHA256).Hash.ToLowerInvariant()
$GameHash = (Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant()
$Receipt = Get-Content -LiteralPath $ReceiptFile -Raw | ConvertFrom-Json
if ($Receipt.physics_exe_sha256 -ne $PhysicsHash -or $Receipt.game_exe_sha256 -ne $GameHash) { throw 'The packaged binaries do not match the successful build receipt.' }
New-Item -ItemType Directory -Path $TestDir | Out-Null
$Started = [DateTime]::UtcNow
$LauncherArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$LauncherScript+'"'),'-LapPhase5Test','-LapAutoExit','-PhysicsPort',"$PhysicsPort",'-LapCaptureDir',('"'+$TestDir+'"'))
$Shell = (Get-Command powershell.exe -ErrorAction Stop).Source
$Launcher = Start-Process -FilePath $Shell -ArgumentList $LauncherArgs -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TestDir 'launcher.stdout.log') -RedirectStandardError (Join-Path $TestDir 'launcher.stderr.log')
$LauncherHandle = $Launcher.Handle
if (-not $Launcher.WaitForExit(780000)) {
    & taskkill.exe /PID $Launcher.Id /T /F | Out-Null
    throw 'The owned packaged acceptance process exceeded thirteen minutes.'
}
$Launcher.WaitForExit(); $Launcher.Refresh()
foreach ($Log in @(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'Logs') -File | Where-Object LastWriteTimeUtc -ge $Started)) {
    if ($Log.Name -like '*-trainer.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'unreal.log') }
    elseif ($Log.Name -like '*-physics.stdout.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'physics.stdout.log') }
    elseif ($Log.Name -like '*-physics.stderr.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'physics.stderr.log') }
}
if ($Launcher.ExitCode -ne 0) { throw "Launcher exit code $($Launcher.ExitCode); evidence is in $TestDir" }
$NativeExits = @(Select-String -LiteralPath (Join-Path $TestDir 'launcher.stdout.log') -Pattern '^PHASE5_PHYSICS_EXIT_CODE=([0-9]+)$')
if ($NativeExits.Count -ne 1 -or [int]$NativeExits[0].Matches[0].Groups[1].Value -ne 0) { throw 'Native graceful exit code zero was not proved.' }
$SessionMarkers = @(Select-String -LiteralPath (Join-Path $TestDir 'launcher.stdout.log') -Pattern '^PHASE5_SESSION_DIR=(.+)$')
if ($SessionMarkers.Count -ne 1) { throw 'Expected exactly one owned native session.' }
$NativeSession = [IO.Path]::GetFullPath($SessionMarkers[0].Matches[0].Groups[1].Value.Trim())
$SessionRoot = [IO.Path]::GetFullPath((Join-Path $PackageRoot 'Sessions'))
if (-not $NativeSession.StartsWith($SessionRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Native session is outside this package.' }
Copy-Item -LiteralPath $NativeSession -Destination (Join-Path $TestDir 'native-sessions') -Recurse
$ReportPath = Join-Path $TestDir 'phase5-input-test.json'
$Report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
$RequiredChecks = @('anatomy_assets_loaded','left_contact_grip','right_contact_grip','traction_deforms','dual_hold','dual_traction_retained','release_both','preset_releases_latched_left','recorded','replay_completed','snapshot','stereo_frames','stereo_alignment','healthy','penetration_bound')
foreach ($Name in $RequiredChecks) { if ($Report.checks.$Name -ne $true) { throw "Missing or failed assertion: $Name" } }
if ($Report.phase -ne 5 -or $Report.passed -ne $true -or @($Report.errors).Count -gt 0) { throw 'Packaged Phase 5 input exercise failed.' }
if (@($Report.checks.PSObject.Properties | Where-Object { $_.Value -ne $true }).Count) { throw 'An input check failed.' }
$Snapshots = @(Get-ChildItem -LiteralPath $TestDir -Filter '*snapshot-*.png')
if ($Snapshots.Count -lt 1) { throw 'No frozen snapshot was written.' }
$Frames = @(Get-ChildItem -LiteralPath (Join-Path $TestDir 'dataset') -Filter 'frame.json' -Recurse)
if ($Frames.Count -lt 24) { throw 'Fewer than 24 frozen stereo frames were exported.' }
$EngineFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'unreal.log') -Pattern 'LAP_PROTOCOL Invalid','Fatal error!','Assertion failed:','Unhandled Exception:' -SimpleMatch)
$PhysicsFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'physics.stderr.log'),(Join-Path $TestDir 'physics.stdout.log') -Pattern '[ERROR]','[FATAL]','FATAL ' -SimpleMatch)
if ($EngineFaults.Count -gt 0 -or $PhysicsFaults.Count -gt 0) { throw 'Protocol or fatal runtime errors in packaged logs.' }
if ((Get-FileHash -LiteralPath $PhysicsExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PhysicsHash -or (Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $GameHash) { throw 'Binaries changed during verification.' }
[ordered]@{
    schema='endoforge.phase5.package-run.v1'; phase=5; passed=$true; run_kind='packaged'
    game_exit_code=$Launcher.ExitCode; native_exit_code=0; physics_exe_sha256=$PhysicsHash
    game_exe_sha256=$GameHash; package_root=$PackageRoot; tested_at_utc=$Started.ToString('o')
    duration_s=([DateTime]::UtcNow-$Started).TotalSeconds; screenshot_count=$Snapshots.Count
    stereo_frames=$Frames.Count; input_report_sha256=(Get-FileHash -LiteralPath $ReportPath -Algorithm SHA256).Hash.ToLowerInvariant()
    scope='Actual packaged PlayerController input exercise; separate geometry and dataset audits are required.'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $TestDir 'phase5-packaged-run.json') -Encoding utf8
Write-Host "Packaged Phase 5 input exercise passed: $TestDir"
$Report | ConvertTo-Json -Depth 8
