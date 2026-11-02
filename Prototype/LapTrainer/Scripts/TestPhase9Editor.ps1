param(
    [string]$EngineRoot = 'E:/UE_5.7',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')][string]$RunName = ('Phase9EditorAcceptance-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $PID),
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47401,
    [ValidateRange(30,1200)][int]$TimeoutSeconds = 780,
    [switch]$DryRun
)
# Editor integration capture only. This does not inherit physical qualification
# or replace the new native suite required by the changed Phase9 mesh.
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$Saved = Join-Path $Root 'Prototype/LapTrainer/Saved'
$Run = [IO.Path]::GetFullPath((Join-Path $Saved $RunName))
if (-not $Run.StartsWith($Saved+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'RunName must remain within this project Saved directory.' }
if (Test-Path -LiteralPath $Run) { throw "Use a fresh RunName to preserve evidence: $Run" }
$Editor = Join-Path ([IO.Path]::GetFullPath($EngineRoot)) 'Engine/Binaries/Win64/UnrealEditor.exe'
$Physics = Join-Path $Root 'Physics/runtime/LapPhysics.exe'
$Project = Join-Path $Root 'Prototype/LapTrainer/LapTrainer.uproject'
$Anatomy = Join-Path $Root 'Assets/Phase9'
$Session = Join-Path $Run 'native-session'
$NativeArguments = @('--phase6','--mesh',('"'+(Join-Path $Anatomy 'physics-mesh.json')+'"'),'--port',"$PhysicsPort",'--session-dir',('"'+$Session+'"'),'--exit-after-client')
$GameArguments = @(('"'+$Project+'"'),'-game','-LapPhase9','-LapPhase9Test','-d3d12','-LapAutoExit',('-LapPhysicsPort='+$PhysicsPort),('-LapAnatomyDir="'+$Anatomy+'"'),('-LapCaptureDir="'+$Run+'"'),'-windowed','-ResX=1920','-ResY=1080','-NoVSync','-nosplash','-nosound','-unattended',('-abslog="'+(Join-Path $Run 'ue.log')+'"'))
if ($DryRun) {
    [ordered]@{phase=9;run_kind='acceptance_test';native_executable=$Physics;native_arguments=$NativeArguments;editor_executable=$Editor;editor_arguments=$GameArguments;port=$PhysicsPort;output=$Run;launches_process=$false;scope='Editor integration capture only; changed Phase9 physical geometry requires separate fresh native qualification.'} | ConvertTo-Json -Depth 5
    return
}
. (Join-Path $Root 'Scripts/Phase9ProcessPolicy.ps1')
$InputPaths = [ordered]@{scene=(Join-Path $Anatomy 'scene.json');physics_mesh=(Join-Path $Anatomy 'physics-mesh.json');native_executable=$Physics;editor_executable=$Editor;editor_module=(Join-Path $Root 'Prototype/LapTrainer/Binaries/Win64/UnrealEditor-LapTrainer.dll')}
foreach ($Path in @($Project)+@($InputPaths.Values)) { if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required editor-capture input missing: $Path" } }
if (Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue) { throw "Port $PhysicsPort is occupied; no existing service will be used or stopped." }
$InputHashes = [ordered]@{}
foreach ($Name in $InputPaths.Keys) { $InputHashes[$Name] = (Get-FileHash -LiteralPath $InputPaths[$Name] -Algorithm SHA256).Hash.ToLowerInvariant() }
New-Item -ItemType Directory -Path $Run | Out-Null
$Native = $null
$Game = $null
$Failure = $null
$NativeGraceful = $false
$GameExit = $null
$NativeExit = $null
$Started = [DateTime]::UtcNow
try {
    $Native = Start-Process -FilePath $Physics -ArgumentList $NativeArguments -WorkingDirectory (Join-Path $Root 'Physics/runtime') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Run 'native.stdout.log') -RedirectStandardError (Join-Path $Run 'native.stderr.log')
    $NativeHandle = $Native.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Native -ExpectedExecutable $Physics -CreatedAfterUtc $Started -Receipt (Join-Path $Run 'native-timer-policy.json') | Out-Null
    $Native.Id | Set-Content -LiteralPath (Join-Path $Run 'native.pid')
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    $Listening = $false
    do {
        $Native.Refresh()
        if ($Native.HasExited) { throw "Owned native process exited before listening: $($Native.ExitCode)" }
        $Owners = @(Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue)
        if (@($Owners | Where-Object OwningProcess -ne $Native.Id).Count) { throw 'Another process acquired the requested native port.' }
        $Listening = @($Owners | Where-Object OwningProcess -eq $Native.Id).Count -ge 1
        if (-not $Listening) { Start-Sleep -Milliseconds 150 }
    } until ($Listening -or [DateTime]::UtcNow -ge $Deadline)
    if (-not $Listening) { throw 'Owned native process did not listen within thirty seconds.' }
    $Game = Start-Process -FilePath $Editor -ArgumentList $GameArguments -WorkingDirectory $Root -WindowStyle Hidden -PassThru
    $GameHandle = $Game.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Game -ExpectedExecutable $Editor -CreatedAfterUtc $Started -Receipt (Join-Path $Run 'ue-timer-policy.json') | Out-Null
    $Game.Id | Set-Content -LiteralPath (Join-Path $Run 'ue.pid')
    if (-not $Game.WaitForExit($TimeoutSeconds*1000)) { throw "Owned UE editor capture exceeded $TimeoutSeconds seconds." }
    $Game.WaitForExit()
    $Game.Refresh()
    $GameExit = $Game.ExitCode
    if ($GameExit -ne 0) { throw "Owned UE editor capture exited with code $GameExit." }
} catch { $Failure = $_.Exception.Message+' at '+$_.ScriptStackTrace } finally {
    if ($Game) {
        $Game.Refresh()
        if (-not $Game.HasExited) { $Game.Kill(); $Game.WaitForExit(); $Failure = (@($Failure,'Owned UE editor required forced termination.') | Where-Object { $_ }) -join '; ' }
        $Game.Dispose()
    }
    if ($Native) {
        if ($Native.WaitForExit(15000)) { $Native.WaitForExit(); $Native.Refresh(); $NativeExit=$Native.ExitCode; $NativeGraceful=$NativeExit -eq 0 }
        else { $Native.Kill(); $Native.WaitForExit(); $Failure = (@($Failure,'Owned native process failed to flush and exit within fifteen seconds.') | Where-Object { $_ }) -join '; ' }
        if (-not $NativeGraceful -and -not $Failure) { $Failure = "Native service exited with code $NativeExit." }
        $Native.Dispose()
    }
}
$AfterHashes = [ordered]@{}
foreach ($Name in $InputPaths.Keys) {
    if (Test-Path -LiteralPath $InputPaths[$Name] -PathType Leaf) { $AfterHashes[$Name] = (Get-FileHash -LiteralPath $InputPaths[$Name] -Algorithm SHA256).Hash.ToLowerInvariant() }
    else { $AfterHashes[$Name] = $null }
    if ($AfterHashes[$Name] -ne $InputHashes[$Name]) { $Failure = (@($Failure,('Editor-capture input changed: '+$Name)) | Where-Object { $_ }) -join '; ' }
}
$Reports = [ordered]@{}
$ReportHashes = [ordered]@{}
try {
    foreach ($Name in @('phase5-input-test.json','phase6-interaction-test.json','phase6-runtime.json')) {
        $Path = Join-Path $Run $Name
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).LastWriteTimeUtc -lt $Started) { throw "Fresh editor report missing: $Name" }
        $Reports[$Name] = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        $ReportHashes[$Name] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Reports[$Name].phase -ne 9 -or $Reports[$Name].mechanics_phase -ne 6) { throw "Wrong phase identity: $Name" }
    }
    if ($Reports['phase5-input-test.json'].passed -ne $true -or $Reports['phase5-input-test.json'].stereo_frames -ne 4) { throw 'Input checks failed or the four internal alignment frames are incomplete.' }
    if ($Reports['phase6-interaction-test.json'].passed -ne $true) { throw 'Editor interaction checks failed.' }
    if ($Reports['phase6-interaction-test.json'].schema -ne 'endoforge.phase9.interaction.v1' -or $Reports['phase6-runtime.json'].schema -ne 'endoforge.phase9.runtime.v1' -or $Reports['phase6-runtime.json'].run_kind -ne 'acceptance_test') { throw 'Editor capture has the wrong runtime/interaction identity.' }
    if ($Reports['phase6-runtime.json'].appearance.diagnostic_neutral_grey -ne $false) { throw 'Diagnostic grey overrides cannot be used for acceptance capture.' }
} catch { $Failure = (@($Failure,$_.Exception.Message) | Where-Object { $_ }) -join '; ' }
$Receipt = [ordered]@{schema='endoforge.phase9.editor-run.v1';phase=9;run_kind='acceptance_test';integration_capture_completed=(-not $Failure);engine_root=$EngineRoot;port=$PhysicsPort;native_arguments=$NativeArguments;editor_arguments=$GameArguments;inputs=$InputPaths;inputs_sha256=$InputHashes;inputs_after_sha256=$AfterHashes;reports_sha256=$ReportHashes;game_exit_code=$GameExit;native_exit_code=$NativeExit;native_graceful_exit=$NativeGraceful;native_session=$Session;duration_s=([DateTime]::UtcNow-$Started).TotalSeconds;error=$Failure;scope='Fresh editor integration capture only. Physical qualification, independent geometry/data audits, visual review and packaged delivery remain separate.'}
$Receipt | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $Run 'editor-run.json') -Encoding utf8
Write-Output ('PHASE9_EDITOR_CAPTURE=' + $Run)
if ($Failure) { throw "$Failure Evidence: $Run" }
