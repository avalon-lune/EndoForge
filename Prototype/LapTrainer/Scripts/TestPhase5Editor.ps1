param(
    [string]$EngineRoot='E:/UE_5.7',
    [string]$RunName='Phase5EditorAcceptance',
    [switch]$SkipDataset,
    [ValidateRange(30,1200)][int]$TimeoutSeconds=780
)
$ErrorActionPreference='Stop'
$Root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$Saved=[IO.Path]::GetFullPath((Join-Path $Root 'Prototype/LapTrainer/Saved'))
$Run=[IO.Path]::GetFullPath((Join-Path $Saved $RunName))
if(!$Run.StartsWith($Saved+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'RunName must remain within this project Saved directory.'}
if(Test-Path -LiteralPath $Run){throw "Use a new RunName to preserve evidence: $Run"}
$Editor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$Physics=Join-Path $Root 'Physics/runtime/LapPhysics.exe'
foreach($File in @($Editor,$Physics)){if(!(Test-Path -LiteralPath $File -PathType Leaf)){throw "Required executable missing: $File"}}
if(Get-NetTCPConnection -LocalPort 47327 -State Listen -ErrorAction SilentlyContinue){throw 'Port 47327 is occupied; the test will not use or stop an existing service.'}
New-Item -ItemType Directory -Path $Run | Out-Null
$Session=Join-Path $Run 'native-session'
$Native=$null; $Game=$null; $Failure=$null; $NativeGraceful=$false; $GameExit=$null; $NativeExit=$null
$Started=[DateTime]::UtcNow
try {
    $Native=Start-Process -FilePath $Physics -ArgumentList @('--phase5','--mesh',('"'+(Join-Path $Root 'Assets/Phase5/physics-mesh.json')+'"'),'--port','47327','--session-dir',('"'+$Session+'"'),'--exit-after-client') -WorkingDirectory (Join-Path $Root 'Physics/runtime') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Run 'native.stdout.log') -RedirectStandardError (Join-Path $Run 'native.stderr.log') -PassThru
    $NativeHandle=$Native.Handle
    $Native.Id | Set-Content -LiteralPath (Join-Path $Run 'native.pid')
    $Deadline=[DateTime]::UtcNow.AddSeconds(30)
    $Listening=$false
    do {
        $Native.Refresh()
        if($Native.HasExited){throw "Owned physics process exited before listening: $($Native.ExitCode)"}
        $Listening=@(Get-NetTCPConnection -LocalPort 47327 -State Listen -ErrorAction SilentlyContinue | Where-Object OwningProcess -eq $Native.Id).Count -eq 1
        if(!$Listening){Start-Sleep -Milliseconds 150}
    } until($Listening -or [DateTime]::UtcNow -ge $Deadline)
    if(!$Listening){throw 'Owned physics process did not listen within thirty seconds.'}
    $Args=@(('"'+(Join-Path $Root 'Prototype/LapTrainer/LapTrainer.uproject')+'"'),'-game','-LapPhase5','-LapPhase5Test','-LapAutoExit','-LapPhysicsPort=47327',('-LapAnatomyDir="'+(Join-Path $Root 'Assets/Phase5')+'"'),('-LapCaptureDir="'+$Run+'"'),'-windowed','-ResX=1280','-ResY=800','-NoVSync','-nosplash','-nosound','-unattended',('-abslog="'+(Join-Path $Run 'ue.log')+'"'))
    if($SkipDataset){$Args+='-LapPhase5SkipDataset'}
    $Game=Start-Process -FilePath $Editor -ArgumentList $Args -WorkingDirectory $Root -WindowStyle Hidden -PassThru
    $GameHandle=$Game.Handle
    $Game.Id | Set-Content -LiteralPath (Join-Path $Run 'ue.pid')
    if(!$Game.WaitForExit($TimeoutSeconds*1000)){throw "Owned UE test exceeded $TimeoutSeconds seconds."}
    $Game.WaitForExit(); $Game.Refresh(); $GameExit=$Game.ExitCode
    if($GameExit -ne 0){throw "UE test process exited with code $GameExit."}
} catch { $Failure=$_.Exception.Message } finally {
    if($Game){$Game.Refresh();if(!$Game.HasExited){Stop-Process -Id $Game.Id -Force; $Game.WaitForExit();$Failure='Owned UE test required forced termination.'}}
    if($Native){
        if($Native.WaitForExit(15000)){$Native.WaitForExit();$Native.Refresh();$NativeExit=$Native.ExitCode;$NativeGraceful=$NativeExit -eq 0}
        else {Stop-Process -Id $Native.Id -Force;$Native.WaitForExit();$Failure='Owned physics service failed to flush and exit within fifteen seconds.'}
        if(!$NativeGraceful -and !$Failure){$Failure="Native service exited with code $NativeExit."}
    }
}
[ordered]@{schema='endoforge.phase5.editor-run.v1';engine_root=$EngineRoot;game_exit_code=$GameExit;native_exit_code=$NativeExit;native_graceful_exit=$NativeGraceful;native_session=$Session;duration_s=([DateTime]::UtcNow-$Started).TotalSeconds;error=$Failure} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Run 'editor-run.json') -Encoding utf8
if($Failure){throw "$Failure Evidence: $Run"}
$Report=Get-Content -LiteralPath (Join-Path $Run 'phase5-input-test.json') -Raw | ConvertFrom-Json
if(!$SkipDataset -and !$Report.passed){throw "Phase 5 input assertions failed. Evidence: $Run"}
Write-Output ('UE exited: '+$GameExit+'; native flushed: '+$NativeGraceful+'; report: '+(Join-Path $Run 'phase5-input-test.json'))
