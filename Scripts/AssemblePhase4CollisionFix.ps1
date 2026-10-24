param(
    [string]$UePackageDirectory = '',
    [string]$PhysicsRuntimeDirectory = '',
    [string]$OutputDirectory = '',
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
# The shared assembler constrains this variant to output/Phase4-CollisionFix.
& (Join-Path $PSScriptRoot 'AssemblePhase4.ps1') -CollisionFix @PSBoundParameters
