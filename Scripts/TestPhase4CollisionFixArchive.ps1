param(
    [string]$ArchivePath = '',
    [string]$RunName = ('phase4-collision-fix-relocated-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'TestPhase4Archive.ps1') -CollisionFix -ArchivePath $ArchivePath -RunName $RunName
