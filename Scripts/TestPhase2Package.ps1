param(
    [string]$PackageRoot = '',
    [string]$RunName = ('phase2-packaged-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
if (-not $PackageRoot) { $PackageRoot = Join-Path $Workspace 'output/Phase2/LapTrainer' }
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$TestRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$TestDir = [IO.Path]::GetFullPath((Join-Path $TestRoot $RunName))
if (-not $TestDir.StartsWith($TestRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Test output must stay under output/verification.' }
if (Test-Path -LiteralPath $TestDir) { throw "Use a fresh test directory: $TestDir" }
$PhysicsExe = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$GameExe = Join-Path $PackageRoot 'LapTrainer/Binaries/Win64/LapTrainer.exe'
$LauncherScript = Join-Path $PackageRoot 'StartTrainer.ps1'
foreach ($Required in @($PhysicsExe,$GameExe,$LauncherScript)) { if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing $Required" } }
$PhysicsHash = (Get-FileHash -LiteralPath $PhysicsExe -Algorithm SHA256).Hash.ToLowerInvariant()
$GameHash = (Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant()
New-Item -ItemType Directory -Path $TestDir | Out-Null
$Started = [DateTime]::UtcNow
$Args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $LauncherScript + '"'),'-LapPhase2Test','-LapAutoExit','-LapCaptureDir',('"' + $TestDir + '"'))
$LauncherShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$Launcher = Start-Process -FilePath $LauncherShell -ArgumentList $Args -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TestDir 'launcher.stdout.log') -RedirectStandardError (Join-Path $TestDir 'launcher.stderr.log')
if (-not $Launcher.WaitForExit(300000)) {
    # This is the process tree created by this test, never a name-based kill.
    & taskkill.exe /PID $Launcher.Id /T /F | Out-Null
    throw 'Packaged acceptance timed out after five minutes.'
}
$Launcher.Refresh()
$RunLogs = @(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'Logs') -File | Where-Object LastWriteTimeUtc -ge $Started)
foreach ($Log in $RunLogs) {
    if ($Log.Name -like '*-trainer.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'unreal.log') }
    elseif ($Log.Name -like '*-physics.stdout.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'physics.stdout.log') }
    elseif ($Log.Name -like '*-physics.stderr.log') { Copy-Item -LiteralPath $Log.FullName -Destination (Join-Path $TestDir 'physics.stderr.log') }
}
if ($Launcher.ExitCode -ne 0) { throw "Packaged launcher failed with $($Launcher.ExitCode); see $TestDir" }
$ReportPath = Join-Path $TestDir 'phase2-input-test.json'
$Report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
if ($Report.phase -ne 2 -or -not $Report.passed) { throw "Packaged contact/input assertions failed: $ReportPath" }
$Screens = @(Get-ChildItem -LiteralPath $TestDir -Filter 'phase2_*.png')
if ($Screens.Count -lt 8) { throw 'Packaged test screenshot sequence is incomplete.' }
$EngineFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'unreal.log') -Pattern 'LAP_PROTOCOL Invalid','Fatal error!','Assertion failed:','Unhandled Exception:' -SimpleMatch)
$PhysicsFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'physics.stderr.log'),(Join-Path $TestDir 'physics.stdout.log') -Pattern '[ERROR]','[FATAL]','FATAL ' -SimpleMatch)
if ($EngineFaults.Count -gt 0 -or $PhysicsFaults.Count -gt 0) { throw 'Protocol or fatal runtime errors found in packaged logs.' }
$TelemetryLines = @(Select-String -LiteralPath (Join-Path $TestDir 'unreal.log') -Pattern 'LAP_SESSION telemetry=(.*); model forces')
if ($TelemetryLines.Count -ne 1) { throw 'Expected exactly one recorded telemetry session.' }
$TelemetrySource = $TelemetryLines[0].Matches[0].Groups[1].Value
if (-not [IO.Path]::IsPathRooted($TelemetrySource)) { $TelemetrySource = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $GameExe) $TelemetrySource)) }
Copy-Item -LiteralPath $TelemetrySource -Destination (Join-Path $TestDir 'phase2-session-acceptance.csv')
$Rows = @(Import-Csv -LiteralPath (Join-Path $TestDir 'phase2-session-acceptance.csv'))
if ($Rows.Count -lt 100 -or @($Rows | Where-Object healthy -ne '1').Count -gt 0) { throw 'Telemetry is incomplete or contains unhealthy states.' }
$Times = @($Rows | ForEach-Object { [double]$_.solve_ms } | Sort-Object)
$P95 = $Times[[Math]::Min($Times.Count - 1,[int][Math]::Ceiling($Times.Count * 0.95) - 1)]
if ((Get-FileHash -LiteralPath $PhysicsExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PhysicsHash -or (Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $GameHash) { throw 'Binaries changed during verification.' }
[ordered]@{
    phase = 2; passed = $true; run_kind = 'packaged'; game_exit_code = $Launcher.ExitCode
    physics_exe_sha256 = $PhysicsHash; game_exe_sha256 = $GameHash; package_root = $PackageRoot
    tested_at_utc = $Started.ToString('o'); duration_s = ([DateTime]::UtcNow - $Started).TotalSeconds
    screenshot_count = $Screens.Count; telemetry_samples = $Rows.Count; telemetry_physics_step_p95_ms = $P95
    engine_protocol_or_fatal_errors = $EngineFaults.Count; physics_errors = $PhysicsFaults.Count
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $TestDir 'phase2-packaged-run.json') -Encoding utf8
Write-Host "Packaged Phase 2 acceptance passed: $TestDir"
$Report | ConvertTo-Json -Depth 8
