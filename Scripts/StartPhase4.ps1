param(
    [ValidateSet('flat','curved')][string]$Specimen = 'flat',
    [string]$ReplayRecording = '',
    [switch]$LapAutoExit,
    [switch]$LapPhase4Test,
    [string]$LapCaptureDir = ''
)
$ErrorActionPreference = 'Stop'
$PackageRoot = $PSScriptRoot
$PhysicsExecutable = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$TrainerExecutable = Join-Path $PackageRoot 'LapTrainer.exe'
$PhysicsPort = 47325
$ConfigPath = Join-Path $PackageRoot ('Physics/configs/' + $Specimen + '.json')
$PhysicsProcess = $null
$TranscriptStarted = $false
$LauncherExitCode = 0

function Test-PhysicsPortListening {
    $Listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return @($Listeners | Where-Object { $_.Port -eq $PhysicsPort }).Count -gt 0
}

function Test-NativeRecordingFlushed {
    if (-not $SessionDirectory -or -not (Test-Path -LiteralPath $SessionDirectory)) { return $true }
    foreach ($States in @(Get-ChildItem -LiteralPath $SessionDirectory -Filter '*-states.jsonl' -File)) {
        $Stem = $States.FullName.Substring(0, $States.FullName.Length - '-states.jsonl'.Length)
        $MetadataPath = $Stem + '-metadata.json'
        $ActionsPath = $Stem + '-actions.json'
        if (-not (Test-Path -LiteralPath $MetadataPath -PathType Leaf) -or -not (Test-Path -LiteralPath $ActionsPath -PathType Leaf)) { return $false }
        try {
            $Metadata = Get-Content -LiteralPath $MetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $Actions = Get-Content -LiteralPath $ActionsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($Metadata.schema -ne 'endoforge.session.v1' -or $Actions.schema -ne 'endoforge.actions.v1' -or
                $Metadata.accepted_steps -ne @($Actions.steps).Count) { return $false }
            # Exclusive access proves the native recording stream has closed;
            # metadata is written only after its successful flush and close.
            $Stream = [IO.File]::Open($States.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
            $Stream.Dispose()
        }
        catch { return $false }
    }
    return $true
}

try {
    foreach ($RequiredExecutable in @($PhysicsExecutable, $TrainerExecutable, $ConfigPath)) {
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
    $SessionDirectory = Join-Path $PackageRoot ('Sessions/' + $RunStamp)
    New-Item -ItemType Directory -Path $SessionDirectory -Force | Out-Null
    if ($ReplayRecording) {
        $ReplayPath = [IO.Path]::GetFullPath($ReplayRecording)
        if (-not (Test-Path -LiteralPath $ReplayPath -PathType Leaf)) { throw 'Replay recording file does not exist.' }
        $Replay = Get-Content -LiteralPath $ReplayPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Replay.schema -ne 'endoforge.actions.v1' -or @($Replay.steps).Count -eq 0 -or @($Replay.steps).Count -gt 180000 -or $null -eq $Replay.config -or $null -eq $Replay.dt_s -or [Math]::Abs([double]$Replay.dt_s - 1.0/30) -gt 1e-12) {
            throw 'ReplayRecording must be a completed endoforge.actions.v1 recording with configuration and steps.'
        }
        Copy-Item -LiteralPath $ReplayPath -Destination (Join-Path $SessionDirectory 'last-session.json')
        Write-Host 'Saved recording staged for native validation. Press F6 to replay the accepted take from its saved specimen configuration.'
    }
    Write-Host ('PHASE4_SESSION_DIR=' + $SessionDirectory)
    Write-Host 'Starting local Phase 4 tissue physics...'
    $PhysicsProcess = Start-Process -FilePath $PhysicsExecutable -WorkingDirectory (Split-Path -Parent $PhysicsExecutable) -ArgumentList @('--port', "$PhysicsPort", '--exit-after-client', '--config', ('"' + $ConfigPath + '"'), '--session-dir', ('"' + $SessionDirectory + '"')) -WindowStyle Hidden -RedirectStandardOutput $PhysicsStdout -RedirectStandardError $PhysicsStderr -PassThru
    # Windows PowerShell 5.1 may return an uncached Process handle. Retain it
    # before the service exits so ExitCode remains queryable after game shutdown.
    $PhysicsProcessHandle = $PhysicsProcess.Handle
    Write-Host ("Physics process ID: {0}" -f $PhysicsProcess.Id)
    $ReadyDeadline = [DateTime]::UtcNow.AddSeconds(45)
    $Ready = $false
    while ([DateTime]::UtcNow -lt $ReadyDeadline) {
        $PhysicsProcess.Refresh()
        if ($PhysicsProcess.HasExited) {
            $PhysicsProcess.WaitForExit()
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
    $TrainerArguments = @('-windowed', '-d3d11', '-LapPhysicsPort=47325', '-ResX=1600', '-ResY=900', ('-abslog="' + $GameLog + '"'))
    if ($LapAutoExit) { $TrainerArguments += '-LapAutoExit' }
    if ($LapPhase4Test) { $TrainerArguments += '-LapPhase4Test' }
    if ($LapCaptureDir) {
        if ($LapCaptureDir.Contains('"')) { throw 'LapCaptureDir must not contain a quotation mark.' }
        $CaptureDirectory = [System.IO.Path]::GetFullPath($LapCaptureDir)
        New-Item -ItemType Directory -Path $CaptureDirectory -Force | Out-Null
        $TrainerArguments += ('-LapCaptureDir="' + $CaptureDirectory.TrimEnd('\') + '"')
    }
    Write-Host 'Starting EndoForge Phase 4. Close the trainer window or press F10 to finish.'
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
            # --exit-after-client flushes the active take on game disconnect and
            # exits normally. Wait for that path before any forced cleanup.
            $PhysicsExited = $PhysicsProcess.WaitForExit(10000)
            if ($PhysicsExited) { $PhysicsProcess.WaitForExit() }
            $PhysicsExitCode = if ($PhysicsExited) { $PhysicsProcess.ExitCode } else { $null }
            $Flushed = Test-NativeRecordingFlushed
            if (-not $PhysicsExited) {
                Write-Warning 'Physics did not exit within ten seconds; forcing shutdown of this owned process. An unfinished recording may be incomplete.'
                $LauncherExitCode = 1
                # Stop only the process object created by this invocation. Never kill by name.
                $PhysicsProcess.Kill()
                $PhysicsProcess.WaitForExit(5000) | Out-Null
            }
            elseif (-not $Flushed) {
                Write-Warning 'Native process exited without complete recording files. Preserve this session for diagnosis.'
                $LauncherExitCode = 1
            }
            elseif ($null -eq $PhysicsExitCode) {
                Write-Warning 'Native exit code is unavailable; this run cannot be verified as successful.'
                $LauncherExitCode = 1
            }
            elseif ($PhysicsExitCode -ne 0) {
                Write-Warning ('Physics exited with code ' + $PhysicsExitCode)
                $LauncherExitCode = 1
            }
            else { Write-Host ('PHASE4_PHYSICS_EXIT_CODE=' + $PhysicsExitCode) }
        }
        catch { $LauncherExitCode = 1; Write-Warning ('Could not clean up this session physics process: ' + $_.Exception.Message) }
        $PhysicsProcess.Dispose()
    }
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
}
exit $LauncherExitCode
