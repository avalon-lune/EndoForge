param(
    [ValidateSet('Physics','Editor','Preview')][string]$Mode = 'Editor',
    [string]$EngineRoot = 'E:/UE_5.7',
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47329,
    [string]$SessionDirectory = '',
    [switch]$DryRun
)
# EndoForge development entry point. Project author/maintainer: Avalon.
# Each endpoint receives the same milestone, absolute anatomy location and port.
# This helper does not select acceptance-test mode or modify model parameters.
$ErrorActionPreference = 'Stop'
$RepositoryRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Anatomy = Join-Path $RepositoryRoot 'Assets/Phase6'
$ProjectFile = Join-Path $RepositoryRoot 'Prototype/LapTrainer/LapTrainer.uproject'
if (-not $SessionDirectory) {
    $SessionDirectory = Join-Path $RepositoryRoot ('tmp/phase6-development/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID)
}
$SessionDirectory = [IO.Path]::GetFullPath($SessionDirectory)
if ($Mode -eq 'Physics') {
    $Executable = Join-Path $RepositoryRoot 'Physics/runtime/LapPhysics.exe'
    $Arguments = @('--phase6','--mesh',(Join-Path $Anatomy 'physics-mesh.json'),'--port',"$PhysicsPort",'--session-dir',$SessionDirectory)
} else {
    $Executable = Join-Path ([IO.Path]::GetFullPath($EngineRoot)) 'Engine/Binaries/Win64/UnrealEditor.exe'
    $Arguments = @($ProjectFile,'-LapPhase6',"-LapPhysicsPort=$PhysicsPort",("-LapAnatomyDir="+$Anatomy),'-d3d12')
    if ($Mode -eq 'Preview') { $Arguments += @('-game','-windowed','-ResX=1920','-ResY=1080') }
}
if ($DryRun) {
    [ordered]@{mode=$Mode;executable=$Executable;arguments=$Arguments;repository=$RepositoryRoot;port=$PhysicsPort;launches_process=$false} | ConvertTo-Json -Depth 4
    return
}
foreach ($Required in @($Executable,$ProjectFile,(Join-Path $Anatomy 'physics-mesh.json'),(Join-Path $Anatomy 'scene.json'))) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing $Required. Follow docs/BUILDING.md before launching." }
}
if ($Mode -eq 'Physics') {
    if (Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $PhysicsPort is occupied. Stop your earlier session or select a matching free port on both endpoints."
    }
    New-Item -ItemType Directory -Path $SessionDirectory -Force | Out-Null
    Write-Host 'Keep this terminal running while using the editor. Finish recording and close Play before stopping the service.'
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Native physics exited with code $LASTEXITCODE" }
} else {
    Write-Host 'Start -Mode Physics in a separate terminal. Full Editor mode uses normal in-process Play; Preview starts the game directly.'
    # Human-invoked editor/preview must be visible for interactive project work.
    $QuotedArguments = @($Arguments | ForEach-Object { '"' + $_ + '"' })
    Start-Process -FilePath $Executable -ArgumentList $QuotedArguments -WorkingDirectory $RepositoryRoot -WindowStyle Normal
}
