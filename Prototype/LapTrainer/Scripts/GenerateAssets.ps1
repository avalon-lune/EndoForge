param([string]$EngineRoot = 'E:/UE_5.7')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectFile = Join-Path $ProjectRoot 'LapTrainer.uproject'
$EditorCmd = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$AssetScript = Join-Path $PSScriptRoot 'generate_assets.py'
$LogDirectory = Join-Path $ProjectRoot 'Saved/Logs'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogFile = Join-Path $LogDirectory 'AssetGeneration.log'
& $EditorCmd $ProjectFile "-ExecutePythonScript=$AssetScript" -unattended -nullrhi -nosplash -nosound -NoP4 -stdout -FullStdOutLogOutput "-abslog=$LogFile"
if ($LASTEXITCODE -ne 0) { throw "Asset generation failed with exit code $LASTEXITCODE. See $LogFile" }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'Content/Maps/TrainingMap.umap'))) {
    throw "TrainingMap was not generated. Inspect $LogFile"
}
Write-Host 'Training map and procedural materials are ready.'
