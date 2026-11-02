param(
    [string]$EngineRoot='E:/UE_5.7',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')][string]$RunName=('Phase9Diagnostic-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $PID),
    [ValidateRange(1025,65535)][int]$PhysicsPort=47391,
    [switch]$SkipDataset,
    [switch]$Video,
    [switch]$ShapeReview,
    [string[]]$ExtraUnrealArguments=@(),
    [ValidateRange(30,1200)][int]$TimeoutSeconds=780,
    [switch]$DryRun
)
$ErrorActionPreference='Stop'
$Root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$Saved=[IO.Path]::GetFullPath((Join-Path $Root 'Prototype/LapTrainer/Saved'))
$Run=[IO.Path]::GetFullPath((Join-Path $Saved $RunName))
if(!$Run.StartsWith($Saved+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'RunName must remain within this project Saved directory.'}
if(Test-Path -LiteralPath $Run){throw "Use a new RunName to preserve evidence: $Run"}
$Editor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$Physics=Join-Path $Root 'Physics/runtime/LapPhysics.exe'
$Anatomy=Join-Path $Root 'Assets/Phase9'
$Session=Join-Path $Run 'native-session'
$NativeArguments=@('--phase6','--mesh',('"'+(Join-Path $Anatomy 'physics-mesh.json')+'"'),'--port',"$PhysicsPort",'--session-dir',('"'+$Session+'"'),'--exit-after-client')
$GameArguments=@(('"'+(Join-Path $Root 'Prototype/LapTrainer/LapTrainer.uproject')+'"'),'-game','-LapPhase9','-LapPhase9Test','-LapDiagnostic','-d3d12','-LapAutoExit',('-LapPhysicsPort='+$PhysicsPort),('-LapAnatomyDir="'+$Anatomy+'"'),('-LapCaptureDir="'+$Run+'"'),'-windowed','-ResX=1920','-ResY=1080','-NoVSync','-nosplash','-nosound','-unattended',('-abslog="'+(Join-Path $Run 'ue.log')+'"'))
if($SkipDataset){$GameArguments+='-LapPhase5SkipDataset'}
if($Video){$GameArguments+='-LapPhase9Video'}
if($ShapeReview){$GameArguments+='-LapPhase9ShapeReview'}
foreach($Argument in $ExtraUnrealArguments){
    if($Argument.Contains('"')){throw 'ExtraUnrealArguments must not contain embedded double quotes.'}
    if($Argument -match '\s'){
        $Equals=$Argument.IndexOf('=')
        if($Argument.StartsWith('-') -and $Equals -gt 0){$GameArguments+=$Argument.Substring(0,$Equals+1)+'"'+$Argument.Substring($Equals+1)+'"'}
        else{$GameArguments+='"'+$Argument+'"'}
    }else{$GameArguments+=$Argument}
}
if($DryRun){
    [ordered]@{phase=9;diagnostic_only=$true;native_executable=$Physics;native_arguments=$NativeArguments;editor_executable=$Editor;editor_arguments=$GameArguments;port=$PhysicsPort;output=$Run;launches_process=$false;scope='Authoring diagnostics only; no acceptance or physical qualification.'}|ConvertTo-Json -Depth 5
    return
}
. (Join-Path $Root 'Scripts/Phase9ProcessPolicy.ps1')
foreach($File in @($Editor,$Physics,(Join-Path $Anatomy 'scene.json'),(Join-Path $Anatomy 'physics-mesh.json'))){if(!(Test-Path -LiteralPath $File -PathType Leaf)){throw "Required diagnostic input missing: $File"}}
if(Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue){throw "Port $PhysicsPort is occupied; diagnostics will not use or stop an existing service."}
$InputPaths=[ordered]@{scene=(Join-Path $Anatomy 'scene.json');physics_mesh=(Join-Path $Anatomy 'physics-mesh.json');native_executable=$Physics}
$InputHashes=[ordered]@{}
foreach($Name in $InputPaths.Keys){$InputHashes[$Name]=(Get-FileHash -LiteralPath $InputPaths[$Name] -Algorithm SHA256).Hash.ToLowerInvariant()}
New-Item -ItemType Directory -Path $Run | Out-Null
$Native=$null; $Game=$null; $Failure=$null; $NativeGraceful=$false; $GameExit=$null; $NativeExit=$null
$Started=[DateTime]::UtcNow
try {
    $Native=Start-Process -FilePath $Physics -ArgumentList $NativeArguments -WorkingDirectory (Join-Path $Root 'Physics/runtime') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Run 'native.stdout.log') -RedirectStandardError (Join-Path $Run 'native.stderr.log') -PassThru
    $NativeHandle=$Native.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Native -ExpectedExecutable $Physics -CreatedAfterUtc $Started -Receipt (Join-Path $Run 'native-timer-policy.json') | Out-Null
    $Native.Id | Set-Content -LiteralPath (Join-Path $Run 'native.pid')
    $Deadline=[DateTime]::UtcNow.AddSeconds(30)
    $Listening=$false
    do {
        $Native.Refresh()
        if($Native.HasExited){throw "Owned physics process exited before listening: $($Native.ExitCode)"}
        $Owners=@(Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue)
        if(@($Owners|Where-Object OwningProcess -ne $Native.Id).Count){throw 'Another process acquired the requested physics port.'}
        $Listening=@($Owners|Where-Object OwningProcess -eq $Native.Id).Count -ge 1
        if(!$Listening){Start-Sleep -Milliseconds 150}
    } until($Listening -or [DateTime]::UtcNow -ge $Deadline)
    if(!$Listening){throw 'Owned physics process did not listen within thirty seconds.'}
    $Game=Start-Process -FilePath $Editor -ArgumentList $GameArguments -WorkingDirectory $Root -WindowStyle Hidden -PassThru
    $GameHandle=$Game.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Game -ExpectedExecutable $Editor -CreatedAfterUtc $Started -Receipt (Join-Path $Run 'ue-timer-policy.json') | Out-Null
    $Game.Id | Set-Content -LiteralPath (Join-Path $Run 'ue.pid')
    if(!$Game.WaitForExit($TimeoutSeconds*1000)){throw "Owned UE test exceeded $TimeoutSeconds seconds."}
    $Game.WaitForExit(); $Game.Refresh(); $GameExit=$Game.ExitCode
    if($GameExit -ne 0){throw "UE test process exited with code $GameExit."}
} catch { $Failure=$_.Exception.Message+' at '+$_.ScriptStackTrace } finally {
    if($Game){$Game.Refresh();if(!$Game.HasExited){Stop-Process -Id $Game.Id -Force; $Game.WaitForExit();$Failure=($Failure+'; Owned UE diagnostic required forced termination.').TrimStart(';',' ')};$Game.Dispose()}
    if($Native){
        if($Native.WaitForExit(15000)){$Native.WaitForExit();$Native.Refresh();$NativeExit=$Native.ExitCode;$NativeGraceful=$NativeExit -eq 0}
        else {Stop-Process -Id $Native.Id -Force;$Native.WaitForExit();$Failure=($Failure+'; Owned physics service failed to flush and exit within fifteen seconds.').TrimStart(';',' ')}
        if(!$NativeGraceful -and !$Failure){$Failure="Native service exited with code $NativeExit."}
        $Native.Dispose()
    }
}
$AfterHashes=[ordered]@{}
foreach($Name in $InputPaths.Keys){
    if(Test-Path -LiteralPath $InputPaths[$Name] -PathType Leaf){$AfterHashes[$Name]=(Get-FileHash -LiteralPath $InputPaths[$Name] -Algorithm SHA256).Hash.ToLowerInvariant()}
    else{$AfterHashes[$Name]=$null}
    if($AfterHashes[$Name] -ne $InputHashes[$Name]){$Failure=(@($Failure,('Diagnostic input changed: '+$Name))|Where-Object{$_})-join '; '}
}
$Report=$null
$ReportHash=$null
$ContactHealthPassed=$false
$RequiredChecks=@('anatomy_assets_loaded','left_contact_grip','right_contact_grip','traction_deforms','dual_hold','release_both','preset_releases_latched_left','dual_traction_retained','healthy','penetration_bound')
try{
    $ReportPath=Join-Path $Run 'phase5-input-test.json'
    if(!(Test-Path -LiteralPath $ReportPath -PathType Leaf) -or (Get-Item -LiteralPath $ReportPath).LastWriteTimeUtc -lt $Started){throw 'Fresh Phase9 input report missing.'}
    $Report=Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
    $ReportHash=(Get-FileHash -LiteralPath $ReportPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($Report.phase -ne 9 -or $Report.mechanics_phase -ne 6){throw 'Diagnostic input report has the wrong phase identity.'}
    $ContactHealthPassed=$true
    foreach($Name in $RequiredChecks){if($Report.checks.$Name -ne $true){$ContactHealthPassed=$false}}
    if(!$ContactHealthPassed){throw 'A required real contact/deformation/release/health check failed or is missing.'}
    if(!$SkipDataset -and $Report.passed -ne $true){throw 'The full diagnostic input sequence reported failed checks.'}
}catch{$Failure=(@($Failure,$_.Exception.Message)|Where-Object{$_})-join '; '}
$DatasetStatus=if($SkipDataset){'skipped_mandatory_alignment_capture'}else{'requested_full_alignment_capture'}
$CheckScope=if($SkipDataset){'contact_deformation_release_and_health_only'}else{'full_diagnostic_input_report'}
[ordered]@{schema='endoforge.phase9.editor-diagnostic.v1';phase=9;diagnostic_only=$true;engine_root=$EngineRoot;port=$PhysicsPort;native_arguments=$NativeArguments;editor_arguments=$GameArguments;inputs=$InputPaths;inputs_sha256=$InputHashes;inputs_after_sha256=$AfterHashes;game_exit_code=$GameExit;native_exit_code=$NativeExit;native_graceful_exit=$NativeGraceful;native_session=$Session;duration_s=([DateTime]::UtcNow-$Started).TotalSeconds;error=$Failure;required_checks_scope=$CheckScope;required_checks=$RequiredChecks;contact_health_checks_passed=$ContactHealthPassed;dataset_skipped=$SkipDataset.IsPresent;dataset_status=$DatasetStatus;mandatory_dataset_checks_skipped=$(if($SkipDataset){@('stereo_frames','stereo_alignment')}else{@()});full_input_report_passed=$(if($Report){$Report.passed}else{$null});source_input_checks=$(if($Report){$Report.checks}else{$null});source_input_errors=$(if($Report){$Report.errors}else{$null});source_input_report_sha256=$ReportHash;captured_stereo_frames=$(if($Report){$Report.stereo_frames}else{$null});full_diagnostic_sequence_passed=(!$SkipDataset -and !$Failure -and $Report.passed -eq $true);scope='Authoring diagnostics only. With SkipDataset, only the named real contact/deformation/release/health checks are required; mandatory alignment checks are explicitly skipped and no full-sequence pass is claimed. Fresh physical and delivery qualification remain separate.'} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $Run 'editor-diagnostic.json') -Encoding utf8
if($Failure){throw "$Failure Evidence: $Run"}
if($SkipDataset){Write-Output ('Phase9 contact/health diagnostics completed; mandatory dataset alignment skipped; full sequence not passed. Evidence: '+$Run)}
else{Write-Output ('Phase9 full diagnostic input sequence completed; report: '+(Join-Path $Run 'phase5-input-test.json'))}

