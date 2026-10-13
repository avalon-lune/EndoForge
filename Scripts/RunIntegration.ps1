param([string]$EngineRoot='E:/UE_5.7', [string]$RunName='editor-integration')
$ErrorActionPreference='Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
$Project = Join-Path $Workspace 'Prototype/LapTrainer/LapTrainer.uproject'
$PhysicsDir = Join-Path $Workspace 'Physics/runtime'
$TestDir = Join-Path $Workspace "output/verification/$RunName"
New-Item -ItemType Directory -Path $TestDir -Force | Out-Null
$Listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
if ($Listeners | Where-Object { $_.Port -eq 47321 }) { throw 'Port 47321 already in use; close the existing trainer first.' }
$PhysicsProc = $null
$UnrealProc = $null
try {
    $PhysicsProc = Start-Process -FilePath (Join-Path $PhysicsDir 'LapPhysics.exe') -WorkingDirectory $PhysicsDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TestDir 'physics.stdout.log') -RedirectStandardError (Join-Path $TestDir 'physics.stderr.log')
    $Ready = $false
    for ($Attempt=0; $Attempt -lt 100; $Attempt++) {
        if ($PhysicsProc.HasExited) { throw "Physics exited $($PhysicsProc.ExitCode)" }
        if ([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq 47321 }) { $Ready=$true; break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $Ready) { throw 'Physics listener did not start.' }
    $Arguments = @('"'+$Project+'"','-game','-windowed','-ResX=1280','-ResY=720','-d3d11','-nosplash','-nosound','-unattended','-LapAutoDemo','-LapAutoExit',('-LapCaptureDir="'+$TestDir+'"'),('-abslog="'+(Join-Path $TestDir 'unreal.log')+'"'),'-ExecCmds="t.MaxFPS 60"')
    $UnrealProc = Start-Process -FilePath (Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe') -ArgumentList $Arguments -WorkingDirectory (Split-Path -Parent $Project) -WindowStyle Hidden -PassThru
    if (-not $UnrealProc.WaitForExit(240000)) { throw 'Unreal integration timed out (4 minutes).' }
    if ($UnrealProc.ExitCode -ne 0) { throw "Unreal exited $($UnrealProc.ExitCode)" }
    $Log = Get-Content -Raw -LiteralPath (Join-Path $TestDir 'unreal.log')
    if ($Log -notmatch 'LAP_AUTODEMO complete') { throw 'Automatic input sequence did not finish.' }
    $Screens = @(Get-ChildItem -LiteralPath $TestDir -Filter '*.png')
    if ($Screens.Count -lt 5) { throw "Only $($Screens.Count) screenshots generated." }
    $Summary = [ordered]@{ completed=$true; game_exit_code=$UnrealProc.ExitCode; screenshot_count=$Screens.Count; mode='Real UE5 rendering + local SOFA; scripted tool input'; timestamp=(Get-Date).ToString('o') }
    $Summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $TestDir 'result.json') -Encoding utf8
    $Log -split "`n" | Where-Object { $_ -match 'LAP_AUTODEMO|physics handshake|Fatal|Error:' } | Select-Object -Last 25
} finally {
    if ($UnrealProc -and -not $UnrealProc.HasExited) { Stop-Process -Id $UnrealProc.Id -ErrorAction SilentlyContinue }
    if ($PhysicsProc -and -not $PhysicsProc.HasExited) { Stop-Process -Id $PhysicsProc.Id -ErrorAction SilentlyContinue }
}
