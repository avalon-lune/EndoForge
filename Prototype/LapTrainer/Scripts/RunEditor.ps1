param([string]$EngineRoot = 'E:/UE_5.7', [switch]$Game)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectFile = Join-Path $ProjectRoot 'LapTrainer.uproject'
$Editor = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$LaunchArguments = @(('"' + $ProjectFile + '"'), '-windowed', '-ResX=1280', '-ResY=720', '-log')
if ($Game) { $LaunchArguments += '-game' }
Start-Process -FilePath $Editor -ArgumentList $LaunchArguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden
