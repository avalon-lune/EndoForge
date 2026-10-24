param(
    [switch]$LapAutoExit,
    [switch]$LapPhase5Test,
    [string]$LapCaptureDir = '',
    [int]$PhysicsPort = 47327,
    [string]$ReplayRecording = ''
)
$ErrorActionPreference = 'Stop'
$PackageRoot = $PSScriptRoot
$PhysicsExecutable = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$TrainerExecutable = Join-Path $PackageRoot 'LapTrainer.exe'
$AnatomyDirectory = Join-Path $PackageRoot 'Assets/Phase5'
$Mesh = Join-Path $AnatomyDirectory 'physics-mesh.json'
$PhysicsProcess = $null
$TranscriptStarted = $false
$LauncherExitCode = 0
try {
    foreach ($Path in @($PhysicsExecutable,$TrainerExecutable,$Mesh,(Join-Path $AnatomyDirectory 'scene.json'))) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing package file: $Path. Extract the complete archive." }
    }
    if ($PhysicsPort -lt 1024 -or $PhysicsPort -gt 65535) { throw 'Invalid physics port' }
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
    Write-Host ('PHASE5_SESSION_DIR=' + $Sessions)
    $NativeArgs = @('--phase5','--port',"$PhysicsPort",'--mesh',('"'+$Mesh+'"'),'--session-dir',('"'+$Sessions+'"'),'--exit-after-client')
    $PhysicsProcess = Start-Process -FilePath $PhysicsExecutable -ArgumentList $NativeArgs -WorkingDirectory (Split-Path -Parent $PhysicsExecutable) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs ($Stamp+'-physics.stdout.log')) -RedirectStandardError (Join-Path $Logs ($Stamp+'-physics.stderr.log')) -PassThru
    $NativeHandle = $PhysicsProcess.Handle
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
    $GameArgs = @('-LapPhase5',('-LapPhysicsPort='+$PhysicsPort),('-LapAnatomyDir="'+$AnatomyDirectory+'"'),'-windowed','-d3d11','-ResX=1920','-ResY=1080',('-abslog="'+(Join-Path $Logs ($Stamp+'-trainer.log'))+'"'))
    if ($LapAutoExit) { $GameArgs += '-LapAutoExit' }
    if ($LapPhase5Test) { $GameArgs += '-LapPhase5Test' }
    if ($LapCaptureDir) {
        if ($LapCaptureDir.Contains('"')) { throw 'Invalid capture path' }
        $CapturePath = [IO.Path]::GetFullPath($LapCaptureDir)
        New-Item -ItemType Directory -Path $CapturePath -Force | Out-Null
        $GameArgs += ('-LapCaptureDir="'+$CapturePath.TrimEnd('\')+'"')
    }
    Write-Host 'Starting EndoForge Phase 5. Close the game or press F10 to finish.'
    $Game = Start-Process -FilePath $TrainerExecutable -WorkingDirectory $PackageRoot -ArgumentList $GameArgs -PassThru -Wait
    $Game.Refresh()
    if ($Game.ExitCode -ne 0) { throw "Game exited with code $($Game.ExitCode)" }
}
catch { $LauncherExitCode=1; Write-Host $_.Exception.Message -ForegroundColor Red }
finally {
    if ($null -ne $PhysicsProcess) {
        try {
            if (-not $PhysicsProcess.WaitForExit(15000)) {
                $PhysicsProcess.Kill(); $PhysicsProcess.WaitForExit(5000) | Out-Null
                $LauncherExitCode=1
                Write-Warning 'Owned physics process did not flush and exit before the timeout.'
            }
            else {
                $PhysicsProcess.WaitForExit()
                Write-Host ('PHASE5_PHYSICS_EXIT_CODE='+$PhysicsProcess.ExitCode)
                if ($PhysicsProcess.ExitCode -ne 0) { $LauncherExitCode=1 }
            }
        }
        catch { $LauncherExitCode=1; Write-Warning $_.Exception.Message }
        $PhysicsProcess.Dispose()
    }
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
}
exit $LauncherExitCode
