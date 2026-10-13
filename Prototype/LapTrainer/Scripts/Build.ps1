param(
    [string]$EngineRoot = 'E:/UE_5.7',
    [ValidateSet('Editor','Game')][string]$Target = 'Editor',
    [ValidateSet('Development','DebugGame','Shipping')][string]$Configuration = 'Development'
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectFile = Join-Path $ProjectRoot 'LapTrainer.uproject'
$BuildTool = Join-Path $EngineRoot 'Engine/Build/BatchFiles/Build.bat'
if (-not (Test-Path -LiteralPath $BuildTool)) { throw "UE build script missing: $BuildTool" }
$TargetName = if ($Target -eq 'Editor') { 'LapTrainerEditor' } else { 'LapTrainer' }
& $BuildTool $TargetName Win64 $Configuration "-Project=$ProjectFile" -WaitMutex -NoHotReloadFromIDE
if ($LASTEXITCODE -ne 0) { throw "UE build failed with exit code $LASTEXITCODE" }
