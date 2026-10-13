param(
    [string]$UePackageDirectory = '',
    [string]$PhysicsRuntimeDirectory = '',
    [string]$OutputDirectory = '',
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
$AssemblyArguments = @{ Phase = 'Phase2'; Replace = $Replace }
if ($UePackageDirectory) { $AssemblyArguments.UePackageDirectory = $UePackageDirectory }
if ($PhysicsRuntimeDirectory) { $AssemblyArguments.PhysicsRuntimeDirectory = $PhysicsRuntimeDirectory }
if ($OutputDirectory) { $AssemblyArguments.OutputDirectory = $OutputDirectory }
& (Join-Path $PSScriptRoot 'AssembleDistribution.ps1') @AssemblyArguments
