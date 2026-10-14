param(
    [switch]$LapAutoExit,
    [switch]$LapPhase3Test,
    [string]$LapCaptureDir = ''
)
$ErrorActionPreference = 'Stop'
$PackageRoot = $PSScriptRoot
$PhysicsExecutable = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$TrainerExecutable = Join-Path $PackageRoot 'LapTrainer.exe'
$PhysicsPort = 47323
$PhysicsProcess = $null
$TranscriptStarted = $false
$LauncherExitCode = 0

function Test-PhysicsPortListening {
    $Listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return @($Listeners | Where-Object { $_.Port -eq $PhysicsPort }).Count -gt 0
}

try {
    foreach ($RequiredExecutable in @($PhysicsExecutable, $TrainerExecutable)) {
        if (-not (Test-Path -LiteralPath $RequiredExecutable -PathType Leaf)) {
            throw "Missing packaged executable: $RequiredExecutable. Extract the complete package before starting."
        }
    }
    if (Test-PhysicsPortListening) {
        throw "Local TCP port $PhysicsPort is already occupied. Close the existing trainer/physics session, then retry. No existing process has been stopped."
    }
    $LogDirectory = Join-Path $PackageRoot 'Logs'
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    $RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $LauncherLog = Join-Path $LogDirectory ($RunStamp + '-launcher.log')
    Start-Transcript -Path $LauncherLog -Force | Out-Null
    $TranscriptStarted = $true
    $PhysicsStdout = Join-Path $LogDirectory ($RunStamp + '-physics.stdout.log')
    $PhysicsStderr = Join-Path $LogDirectory ($RunStamp + '-physics.stderr.log')
    Write-Host 'Starting local Phase 3 tissue physics...'
    $PhysicsProcess = Start-Process -FilePath $PhysicsExecutable -WorkingDirectory (Split-Path -Parent $PhysicsExecutable) -ArgumentList @('--port', "$PhysicsPort") -WindowStyle Hidden -RedirectStandardOutput $PhysicsStdout -RedirectStandardError $PhysicsStderr -PassThru
    Write-Host ("Physics process ID: {0}" -f $PhysicsProcess.Id)
    $ReadyDeadline = [DateTime]::UtcNow.AddSeconds(45)
    $Ready = $false
    while ([DateTime]::UtcNow -lt $ReadyDeadline) {
        $PhysicsProcess.Refresh()
        if ($PhysicsProcess.HasExited) {
            throw "SOFA exited during startup (code $($PhysicsProcess.ExitCode)). See $PhysicsStderr"
        }
        # Reading the local listener table does not open or consume a SOFA client session.
        if (Test-PhysicsPortListening) {
            $Owner = @(Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue)
            if ($Owner.Count -gt 0 -and @($Owner | Where-Object { $_.OwningProcess -eq $PhysicsProcess.Id }).Count -eq 0) {
                throw "Another process acquired port $PhysicsPort while SOFA was starting. No other process will be stopped."
            }
            # Process redirection can buffer stdout until exit. Confirm readiness from
            # the listening socket owner instead of waiting for a log-file marker.
            if (@($Owner | Where-Object { $_.OwningProcess -eq $PhysicsProcess.Id }).Count -gt 0) {
                $Ready = $true
                break
            }
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $Ready) { throw "SOFA did not become ready within 45 seconds. See $PhysicsStdout and $PhysicsStderr" }
    $GameLog = Join-Path $LogDirectory ($RunStamp + '-trainer.log')
    $TrainerArguments = @('-windowed', '-d3d11', '-LapPhysicsPort=47323', '-ResX=1600', '-ResY=900', ('-abslog="' + $GameLog + '"'))
    if ($LapAutoExit) { $TrainerArguments += '-LapAutoExit' }
    if ($LapPhase3Test) { $TrainerArguments += '-LapPhase3Test' }
    if ($LapCaptureDir) {
        if ($LapCaptureDir.Contains('"')) { throw 'LapCaptureDir must not contain a quotation mark.' }
        $CaptureDirectory = [System.IO.Path]::GetFullPath($LapCaptureDir)
        New-Item -ItemType Directory -Path $CaptureDirectory -Force | Out-Null
        $TrainerArguments += ('-LapCaptureDir="' + $CaptureDirectory.TrimEnd('\') + '"')
    }
    Write-Host 'Starting EndoForge Phase 3. Close the trainer window or press F10 to finish.'
    # -Wait waits for the bootstrap process and its descendants, so physics stays alive
    # until the actual game process exits. The user-facing game window remains visible.
    $TrainerProcess = Start-Process -FilePath $TrainerExecutable -WorkingDirectory $PackageRoot -ArgumentList $TrainerArguments -PassThru -Wait
    $TrainerProcess.Refresh()
    if ($TrainerProcess.ExitCode -ne 0) { throw "LapTrainer exited with code $($TrainerProcess.ExitCode). See $GameLog" }
    Write-Host ("Session finished. Logs: {0}" -f $LogDirectory)
}
catch {
    $LauncherExitCode = 1
    Write-Host ('LapTrainer could not complete: ' + $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($null -ne $PhysicsProcess) {
        try {
            $PhysicsProcess.Refresh()
            if (-not $PhysicsProcess.HasExited) {
                # Stop only the process object created by this invocation. Never kill by name.
                $PhysicsProcess.Kill()
                $PhysicsProcess.WaitForExit(5000) | Out-Null
            }
        }
        catch { Write-Warning ('Could not clean up this session physics process: ' + $_.Exception.Message) }
        $PhysicsProcess.Dispose()
    }
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
}
exit $LauncherExitCode
