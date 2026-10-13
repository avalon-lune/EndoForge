param(
    [string]$EngineRoot = 'E:/UE_5.7',
    [string]$OutputDirectory = '',
    [ValidateSet('Development','Shipping')][string]$Configuration = 'Development'
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectFile = Join-Path $ProjectRoot 'LapTrainer.uproject'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path (Split-Path -Parent $ProjectRoot) 'Packages' }
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$UatTool = Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat'
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'Content/Maps/TrainingMap.umap'))) {
    throw 'TrainingMap is missing. Run Build.ps1 then GenerateAssets.ps1 first.'
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
& $UatTool BuildCookRun "-project=$ProjectFile" -noP4 -platform=Win64 "-clientconfig=$Configuration" -build -cook '-map=/Game/Maps/TrainingMap' -stage -pak -iostore -package -archive "-archivedirectory=$OutputDirectory" -prereqs -nodebuginfo -utf8output -unattended
if ($LASTEXITCODE -ne 0) { throw "UE packaging failed with exit code $LASTEXITCODE" }
Write-Host "UE package ready: $OutputDirectory"
Write-Host 'The SOFA physics executable and its runtime dependencies must also be included by the distribution assembly step.'
