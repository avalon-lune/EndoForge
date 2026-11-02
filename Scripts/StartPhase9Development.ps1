param(
    [ValidateSet('Physics','Editor','Preview')][string]$Mode = 'Editor',
    [string]$EngineRoot = 'E:/UE_5.7',
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47391,
    [string]$SessionDirectory = '',
    [string]$CaptureDirectory = '',
    [switch]$Diagnostic,
    [string[]]$ExtraUnrealArguments = @(),
    [switch]$DryRun
)
# Author/maintainer: Avalon. No build, import or qualification is implicit.
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Anatomy = Join-Path $Root 'Assets/Phase9'
$Project = Join-Path $Root 'Prototype/LapTrainer/LapTrainer.uproject'
if (-not $SessionDirectory) { $SessionDirectory = Join-Path $Root ('tmp/phase9/development/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $PID) }
$SessionDirectory = [IO.Path]::GetFullPath($SessionDirectory)
function Format-LaunchArgument([string]$Argument) {
    if ($Argument.Contains('"')) { throw 'Arguments must not contain embedded double quotes.' }
    if ($Argument -notmatch '\s') { return $Argument }
    $Equals = $Argument.IndexOf('=')
    if ($Argument.StartsWith('-') -and $Equals -gt 0) { return $Argument.Substring(0,$Equals+1) + '"' + $Argument.Substring($Equals+1) + '"' }
    return '"' + $Argument + '"'
}
if ($Mode -eq 'Physics') {
    $Executable = Join-Path $Root 'Physics/runtime/LapPhysics.exe'
    # Phase6 denotes the compatible native protocol/solver, not inherited
    # qualification. This explicit changed Phase9 mesh needs fresh checks.
    $Arguments = @('--phase6','--mesh',(Join-Path $Anatomy 'physics-mesh.json'),'--port',"$PhysicsPort",'--session-dir',$SessionDirectory)
    $LaunchArguments = $null
} else {
    $Executable = Join-Path ([IO.Path]::GetFullPath($EngineRoot)) 'Engine/Binaries/Win64/UnrealEditor.exe'
    $Arguments = @($Project.Replace('\','/'),'-LapPhase9',"-LapPhysicsPort=$PhysicsPort",('-LapAnatomyDir=' + $Anatomy.Replace('\','/')),'-d3d12')
    if ($Mode -eq 'Preview') { $Arguments += @('-game','-windowed','-ResX=1920','-ResY=1080') }
    if ($Diagnostic) { $Arguments += '-LapDiagnostic' }
    if ($CaptureDirectory) { $Arguments += '-LapCaptureDir=' + ([IO.Path]::GetFullPath($CaptureDirectory)).Replace('\','/') }
    $Arguments += $ExtraUnrealArguments
    $LaunchArguments = @($Arguments | ForEach-Object { Format-LaunchArgument $_ })
}
if ($DryRun) {
    [ordered]@{phase=9;mode=$Mode;executable=$Executable;arguments=$Arguments;command_line_arguments=$LaunchArguments;repository=$Root;anatomy=$Anatomy;port=$PhysicsPort;diagnostic=$Diagnostic.IsPresent;physical_qualification='fresh Phase9 qualification required';launches_process=$false} | ConvertTo-Json -Depth 5
    return
}
foreach ($Path in @($Executable,$Project,(Join-Path $Anatomy 'physics-mesh.json'),(Join-Path $Anatomy 'scene.json'))) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing development input: $Path. See Scripts/README-Phase9.md." }
}
if ($Mode -eq 'Physics') {
    if (Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue) { throw "Port $PhysicsPort is occupied. No existing process was stopped; use the same free port on both endpoints." }
    if (Test-Path -LiteralPath $SessionDirectory) { throw 'Use a fresh SessionDirectory to preserve previous recordings.' }
    New-Item -ItemType Directory -Path $SessionDirectory | Out-Null
    Write-Host ('PHASE9_SESSION_DIR=' + $SessionDirectory)
    Write-Host 'Keep this terminal running while using the editor. Finish recording and close Play before stopping the service.'
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Native physics exited with code $LASTEXITCODE" }
} else {
    Write-Host 'Start -Mode Physics in a separate terminal. Editor uses normal in-process Play; Preview starts the game directly.'
    Start-Process -FilePath $Executable -ArgumentList $LaunchArguments -WorkingDirectory $Root -WindowStyle Normal
}
