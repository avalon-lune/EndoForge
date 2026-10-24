param(
    [string]$EngineRoot = 'E:/UE_5.7',
    [string]$RunName = ('phase3-editor-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
function Get-CompatibilitySourceHashes([string]$Root) {
    $ProjectRoot = Join-Path $Root 'Prototype/LapTrainer'
    $Files = @(Get-Item -LiteralPath (Join-Path $ProjectRoot 'LapTrainer.uproject'))
    foreach ($Name in @('Source','Config','Content')) { $Files += @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot $Name) -File -Recurse) }
    $Hashes = [ordered]@{}
    foreach ($File in ($Files | Sort-Object FullName)) {
        $Hashes[$File.FullName.Substring($Root.Length + 1).Replace('\','/')] = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $Hashes
}
$PhysicsHash = (Get-FileHash -LiteralPath (Join-Path $Workspace 'Physics/runtime/LapPhysics.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
$ModuleHash = (Get-FileHash -LiteralPath (Join-Path $Workspace 'Prototype/LapTrainer/Binaries/Win64/UnrealEditor-LapTrainer.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
$Project = Join-Path $Workspace 'Prototype/LapTrainer/LapTrainer.uproject'
$PhysicsDir = Join-Path $Workspace 'Physics/runtime'
$TestRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$TestDir = [IO.Path]::GetFullPath((Join-Path $TestRoot $RunName))
if (-not $TestDir.StartsWith($TestRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Test output must stay under output/verification.'
}
if (Test-Path -LiteralPath $TestDir) { throw "Use a fresh test directory: $TestDir" }
New-Item -ItemType Directory -Path $TestDir -Force | Out-Null
$Listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
if (@($Listeners | Where-Object Port -eq 47323).Count -gt 0) { throw 'Port 47323 is in use. Existing processes were not stopped.' }
$PhysicsProc = $null
$UnrealProc = $null
try {
    $PhysicsProc = Start-Process -FilePath (Join-Path $PhysicsDir 'LapPhysics.exe') -ArgumentList @('--phase3','--port','47323') -WorkingDirectory $PhysicsDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TestDir 'physics.stdout.log') -RedirectStandardError (Join-Path $TestDir 'physics.stderr.log')
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 450; $Attempt++) {
        $PhysicsProc.Refresh()
        if ($PhysicsProc.HasExited) { throw "Physics exited during startup: $($PhysicsProc.ExitCode)" }
        $Owner = @(Get-NetTCPConnection -LocalPort 47323 -State Listen -ErrorAction SilentlyContinue)
        if (@($Owner | Where-Object OwningProcess -eq $PhysicsProc.Id).Count -gt 0) { $Ready = $true; break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $Ready) { throw 'Physics did not listen within 45 seconds.' }
    $Arguments = @(('"' + $Project + '"'), '-game', '-windowed', '-ResX=1600', '-ResY=900', '-d3d11', '-nosplash', '-nosound', '-unattended', '-LapPhase3', '-LapPhysicsPort=47323', '-LapPhase3Test', '-LapAutoExit', ('-LapCaptureDir="' + $TestDir + '"'), ('-abslog="' + (Join-Path $TestDir 'unreal.log') + '"'), '-ExecCmds="t.MaxFPS 60"')
    $UnrealProc = Start-Process -FilePath (Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe') -ArgumentList $Arguments -WorkingDirectory (Split-Path -Parent $Project) -WindowStyle Hidden -PassThru
    if (-not $UnrealProc.WaitForExit(780000)) { throw 'Phase 3 integration exceeded thirteen minutes.' }
    if ($UnrealProc.ExitCode -ne 0) { throw "UE exited with code $($UnrealProc.ExitCode)" }
    $ReportPath = Join-Path $TestDir 'phase3-input-test.json'
    if (-not (Test-Path -LiteralPath $ReportPath)) { throw "Missing test report: $ReportPath" }
    $Report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
    if ($Report.phase -ne 3 -or $Report.passed -ne $true -or @($Report.failures).Count -gt 0) { throw "Phase 3 input/cutting assertions failed; inspect $ReportPath" }
    if (-not $Report.checks -or @($Report.checks.PSObject.Properties | Where-Object { $_.Value -ne $true }).Count -gt 0) { throw 'Every Phase 3 input assertion must pass.' }
    if ($Report.checks.regular_exercise_without_safety_stops -ne $true -or $null -eq $Report.metrics.safety_stop_count -or $Report.metrics.safety_stop_count -ne 0) { throw 'Integration acceptance must explicitly prove zero protection events.' }
    $Screens = @(Get-ChildItem -LiteralPath $TestDir -Filter '*.png')
    if ($Screens.Count -lt 7) { throw "Only $($Screens.Count) screenshots; expected the complete Phase 3 sequence." }
    $EngineFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'unreal.log') -Pattern 'LAP_PROTOCOL Invalid','Fatal error!','Assertion failed:','Unhandled Exception:' -SimpleMatch)
    $PhysicsFaults = @(Select-String -LiteralPath (Join-Path $TestDir 'physics.stderr.log'),(Join-Path $TestDir 'physics.stdout.log') -Pattern '[ERROR]','[FATAL]','FATAL ' -SimpleMatch)
    if ($EngineFaults.Count -gt 0 -or $PhysicsFaults.Count -gt 0) { throw 'Protocol or fatal runtime errors found in integration logs.' }
    [ordered]@{ phase = 3; passed = $true; physics_exe_sha256=$PhysicsHash; module_sha256=$ModuleHash; source_files_sha256=(Get-CompatibilitySourceHashes $Workspace); test_directory = $TestDir; game_exit_code = $UnrealProc.ExitCode; screenshot_count = $Screens.Count; engine_protocol_or_fatal_errors = $EngineFaults.Count; physics_errors = $PhysicsFaults.Count; timestamp = (Get-Date).ToString('o') } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $TestDir 'integration-result.json') -Encoding utf8
    Write-Host "Phase 3 integration passed: $TestDir"
    $Report | ConvertTo-Json -Depth 6
}
finally {
    if ($UnrealProc -and -not $UnrealProc.HasExited) { Stop-Process -Id $UnrealProc.Id -ErrorAction SilentlyContinue }
    if ($PhysicsProc -and -not $PhysicsProc.HasExited) { Stop-Process -Id $PhysicsProc.Id -ErrorAction SilentlyContinue }
}
