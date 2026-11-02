param(
    [ValidateSet('Physics','Editor','Preview')][string]$Mode = 'Editor',
    [string]$EngineRoot = 'E:/UE_5.7',
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47351,
    [string]$SessionDirectory = '',
    [switch]$DryRun
)
# EndoForge Phase8 development entry point. Author/maintainer: Avalon.
# Each endpoint receives the same milestone, absolute anatomy location and port.
# This helper does not select acceptance-test mode or modify model parameters.
$ErrorActionPreference = 'Stop'
$RepositoryRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Anatomy = Join-Path $RepositoryRoot 'Assets/Phase8'
$ProjectFile = Join-Path $RepositoryRoot 'Prototype/LapTrainer/LapTrainer.uproject'
if (-not $SessionDirectory) {
    $SessionDirectory = Join-Path $RepositoryRoot ('tmp/phase8-development/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID)
}
$SessionDirectory = [IO.Path]::GetFullPath($SessionDirectory)
if ($Mode -eq 'Physics') {
    $Executable = Join-Path $RepositoryRoot 'Physics/runtime/LapPhysics.exe'
    # A shipped Source/ checkout uses its sibling packaged native runtime.
    # Only the exact executable/mesh named by that Phase8 build is eligible.
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        $DeliveryRoot = Split-Path -Parent $RepositoryRoot
        $DeliveryReceipt = Join-Path $DeliveryRoot 'phase8-build-receipt.json'
        $BundledExecutable = Join-Path $DeliveryRoot 'Physics/LapPhysics.exe'
        if ((Split-Path -Leaf $RepositoryRoot) -eq 'Source' -and (Test-Path -LiteralPath $DeliveryReceipt) -and (Test-Path -LiteralPath $BundledExecutable)) {
            $Build = Get-Content -LiteralPath $DeliveryReceipt -Raw | ConvertFrom-Json
            if ($Build.phase -ne 8 -or $Build.schema -ne 'endoforge.phase8.build.v1' -or
                (Get-FileHash -LiteralPath $BundledExecutable -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Build.physics_exe_sha256 -or
                (Get-FileHash -LiteralPath (Join-Path $Anatomy 'physics-mesh.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Build.native_inheritance.physical_asset_sha256) {
                throw 'The sibling packaged runtime does not match this Phase8 editable scene.'
            }
            $Executable = $BundledExecutable
        }
    }
    $Arguments = @('--phase6','--mesh',(Join-Path $Anatomy 'physics-mesh.json'),'--port',"$PhysicsPort",'--session-dir',$SessionDirectory)
} else {
    $Executable = Join-Path ([IO.Path]::GetFullPath($EngineRoot)) 'Engine/Binaries/Win64/UnrealEditor.exe'
    $ProjectArgument = $ProjectFile.Replace('\','/')
    $AnatomyArgument = $Anatomy.Replace('\','/')
    $Arguments = @($ProjectArgument,'-LapPhase8',"-LapPhysicsPort=$PhysicsPort",("-LapAnatomyDir="+$AnatomyArgument),'-d3d12')
    if ($Mode -eq 'Preview') { $Arguments += @('-game','-windowed','-ResX=1920','-ResY=1080') }
    # UE parses values from its command line; quote the value after '=' for paths with spaces.
    $LaunchArguments = @($Arguments | ForEach-Object {
        if ($_.StartsWith('-LapAnatomyDir=')) { '-LapAnatomyDir="' + $AnatomyArgument + '"' }
        elseif ($_ -match '\s') { '"' + $_ + '"' }
        else { $_ }
    })
}
if ($DryRun) {
    [ordered]@{mode=$Mode;executable=$Executable;arguments=$Arguments;command_line_arguments=$(if($Mode -eq 'Physics'){$null}else{$LaunchArguments});repository=$RepositoryRoot;port=$PhysicsPort;launches_process=$false} | ConvertTo-Json -Depth 4
    return
}
foreach ($Required in @($Executable,$ProjectFile,(Join-Path $Anatomy 'physics-mesh.json'),(Join-Path $Anatomy 'scene.json'))) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing $Required. Follow docs/PHASE8.md before launching." }
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
    Start-Process -FilePath $Executable -ArgumentList $LaunchArguments -WorkingDirectory $RepositoryRoot -WindowStyle Normal
}
