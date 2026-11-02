param(
    [string]$PackageRoot = $PSScriptRoot,
    [switch]$LapAutoExit,
    [switch]$LapPhase9Test,
    [switch]$Diagnostic,
    [switch]$Video,
    [switch]$ShapeReview,
    [string]$LapCaptureDir = '',
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47411,
    [string]$ReplayRecording = '',
    [string[]]$ExtraUnrealArguments = @(),
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$PhysicsExecutable = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$TrainerExecutable = Join-Path $PackageRoot 'LapTrainer/Binaries/Win64/LapTrainer.exe'
$AnatomyDirectory = Join-Path $PackageRoot 'Assets/Phase9'
$Mesh = Join-Path $AnatomyDirectory 'physics-mesh.json'
if ($DryRun) {
    [ordered]@{phase=9;package_root=$PackageRoot;physics_executable=$PhysicsExecutable;trainer_executable=$TrainerExecutable;native_mode='--phase6';mesh=$Mesh;anatomy=$AnatomyDirectory;ue_selector='-LapPhase9';port=$PhysicsPort;diagnostic=($Diagnostic -or $LapPhase9Test -or $Video -or $ShapeReview);extra_unreal_arguments=$ExtraUnrealArguments;physical_qualification='fresh Phase9 qualification required';launches_process=$false} | ConvertTo-Json -Depth 5
    return
}
if (($Video -or $ShapeReview) -and -not $LapPhase9Test) { throw '-Video and -ShapeReview require -LapPhase9Test for the bounded diagnostic sequence.' }
. (Join-Path $PSScriptRoot 'Phase9ProcessPolicy.ps1')
$PhysicsProcess = $null
$Game = $null
$TranscriptStarted = $false
$LauncherExitCode = 0
try {
    foreach ($Path in @($PhysicsExecutable,$TrainerExecutable,$Mesh,(Join-Path $AnatomyDirectory 'scene.json'))) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing package file: $Path. Extract the complete archive." }
    }
    if ($PhysicsPort -lt 1025 -or $PhysicsPort -gt 65535) { throw 'Invalid physics port' }
    $Listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if (@($Listeners | Where-Object Port -eq $PhysicsPort).Count) { throw "Port $PhysicsPort is already in use; no existing process was stopped." }
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $Logs = Join-Path $PackageRoot 'Logs'
    $Sessions = Join-Path $PackageRoot ('Sessions/' + $Stamp)
    New-Item -ItemType Directory -Path $Logs,$Sessions -Force | Out-Null
    Start-Transcript -Path (Join-Path $Logs ($Stamp+'-launcher.log')) | Out-Null
    $TranscriptStarted = $true
    if ($ReplayRecording) {
        $ReplayPath = [IO.Path]::GetFullPath($ReplayRecording)
        if (-not (Test-Path -LiteralPath $ReplayPath -PathType Leaf)) { throw 'Recording not found' }
        Copy-Item -LiteralPath $ReplayPath -Destination (Join-Path $Sessions 'last-session.json')
        Write-Host 'Recording staged. F6 requests native model/version validation and replay.'
    }
    Write-Host ('PHASE9_SESSION_DIR=' + $Sessions)
    $NativeArgs = @('--phase6','--port',"$PhysicsPort",'--mesh',('"'+$Mesh+'"'),'--session-dir',('"'+$Sessions+'"'),'--exit-after-client')
    $OwnedLaunchStarted = [DateTime]::UtcNow
    $PhysicsProcess = Start-Process -FilePath $PhysicsExecutable -ArgumentList $NativeArgs -WorkingDirectory (Split-Path -Parent $PhysicsExecutable) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs ($Stamp+'-physics.stdout.log')) -RedirectStandardError (Join-Path $Logs ($Stamp+'-physics.stderr.log')) -PassThru
    $NativeHandle = $PhysicsProcess.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $PhysicsProcess -ExpectedExecutable $PhysicsExecutable -CreatedAfterUtc $OwnedLaunchStarted -Receipt (Join-Path $Logs ($Stamp+'-physics-timer-policy.json')) | Out-Null
    $Deadline = [DateTime]::UtcNow.AddSeconds(60)
    $Ready = $false
    while ([DateTime]::UtcNow -lt $Deadline) {
        $PhysicsProcess.Refresh()
        if ($PhysicsProcess.HasExited) { throw "Physics exited during startup: $($PhysicsProcess.ExitCode)" }
        $Owners = @(Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue)
        if (@($Owners | Where-Object OwningProcess -eq $PhysicsProcess.Id).Count) { $Ready=$true; break }
        if ($Owners.Count) { throw 'Another process acquired the requested port' }
        Start-Sleep -Milliseconds 150
    }
    if (-not $Ready) { throw 'Physics startup timed out' }
    $AnatomyArgument = $AnatomyDirectory.Replace('\','/')
    $LogArgument = (Join-Path $Logs ($Stamp+'-trainer.log')).Replace('\','/')
    $GameArgs = @('-LapPhase9',('-LapPhysicsPort='+$PhysicsPort),('-LapAnatomyDir="'+$AnatomyArgument+'"'),'-windowed','-d3d12','-ResX=1920','-ResY=1080',('-abslog="'+$LogArgument+'"'))
    if ($LapAutoExit) { $GameArgs += '-LapAutoExit' }
    if ($LapPhase9Test) { $GameArgs += '-LapPhase9Test' }
    if ($Diagnostic -or $LapPhase9Test -or $Video -or $ShapeReview) { $GameArgs += '-LapDiagnostic' }
    if ($Video) { $GameArgs += '-LapPhase9Video' }
    if ($ShapeReview) { $GameArgs += '-LapPhase9ShapeReview' }
    foreach ($Argument in $ExtraUnrealArguments) {
        if ($Argument.Contains('"')) { throw 'ExtraUnrealArguments must not contain embedded double quotes.' }
        if ($Argument -match '\s') {
            $Equals = $Argument.IndexOf('=')
            if ($Argument.StartsWith('-') -and $Equals -gt 0) { $GameArgs += $Argument.Substring(0,$Equals+1) + '"' + $Argument.Substring($Equals+1) + '"' }
            else { $GameArgs += '"' + $Argument + '"' }
        } else { $GameArgs += $Argument }
    }
    if ($LapCaptureDir) {
        if ($LapCaptureDir.Contains('"')) { throw 'Invalid capture path' }
        $CapturePath = [IO.Path]::GetFullPath($LapCaptureDir)
        New-Item -ItemType Directory -Path $CapturePath -Force | Out-Null
        $GameArgs += ('-LapCaptureDir="'+$CapturePath.TrimEnd('\').Replace('\','/')+'"')
    }
    Write-Host 'Starting EndoForge Phase 9. Close the game or press F10 to finish.'
    # Launch the actual game endpoint so its handle, timing policy and exit code
    # belong to the simulation window rather than the bootstrap executable.
    $GameWindow = if ($LapPhase9Test) { 'Hidden' } else { 'Normal' }
    $Game = Start-Process -FilePath $TrainerExecutable -WorkingDirectory $PackageRoot -ArgumentList $GameArgs -WindowStyle $GameWindow -PassThru
    $GameHandle = $Game.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Game -ExpectedExecutable $TrainerExecutable -CreatedAfterUtc $OwnedLaunchStarted -Receipt (Join-Path $Logs ($Stamp+'-trainer-timer-policy.json')) | Out-Null
    $Game.WaitForExit()
    $Game.Refresh()
    if ($Game.ExitCode -ne 0) { throw "Game exited with code $($Game.ExitCode)" }
}
catch { $LauncherExitCode=1; Write-Host $_.Exception.Message -ForegroundColor Red }
finally {
    if ($null -ne $Game) {
        try {
            $Game.Refresh()
            if (-not $Game.HasExited) {
                # Only this launcher's actual game handle is eligible for cleanup.
                $Game.CloseMainWindow() | Out-Null
                if (-not $Game.WaitForExit(5000)) { $Game.Kill(); $Game.WaitForExit() }
                $LauncherExitCode=1
                Write-Warning 'Owned game process was closed after an abnormal launcher exit.'
            }
        }
        catch { $LauncherExitCode=1; Write-Warning $_.Exception.Message }
        finally { $Game.Dispose() }
    }
    if ($null -ne $PhysicsProcess) {
        try {
            if (-not $PhysicsProcess.WaitForExit(15000)) {
                $PhysicsProcess.Kill(); $PhysicsProcess.WaitForExit(5000) | Out-Null
                $LauncherExitCode=1
                Write-Warning 'Owned physics process did not flush and exit before the timeout.'
            }
            else {
                $PhysicsProcess.WaitForExit()
                Write-Host ('PHASE9_PHYSICS_EXIT_CODE='+$PhysicsProcess.ExitCode)
                if ($PhysicsProcess.ExitCode -ne 0) { $LauncherExitCode=1 }
            }
        }
        catch { $LauncherExitCode=1; Write-Warning $_.Exception.Message }
        $PhysicsProcess.Dispose()
    }
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
}
exit $LauncherExitCode
