param([string]$EngineRoot = 'E:/UE_5.7', [string]$RunName = ('phase4-protocol-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'Phase4Evidence.ps1')
$VerifyRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$TestDir = [IO.Path]::GetFullPath((Join-Path $VerifyRoot $RunName))
if (-not $TestDir.StartsWith($VerifyRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid verification destination' }
if (Test-Path -LiteralPath $TestDir) { throw 'Choose a new protocol test directory' }
New-Item -ItemType Directory -Path $TestDir | Out-Null
$Project = Join-Path $Workspace 'Prototype/LapTrainer/LapTrainer.uproject'
$Module = Join-Path $Workspace 'Prototype/LapTrainer/Binaries/Win64/UnrealEditor-LapTrainer.dll'
$ModuleHash = (Get-FileHash -LiteralPath $Module -Algorithm SHA256).Hash.ToLowerInvariant()
$Args = @(('"' + $Project + '"'), '-nullrhi', '-nosound', '-unattended', '-nop4', '-nosplash',
    '-ExecCmds="Automation RunTests EndoForge.Phase4.AtomicSnapshotProtocol"',
    '-TestExit="Automation Test Queue Empty"', ('-ReportExportPath="' + $TestDir + '"'),
    ('-abslog="' + (Join-Path $TestDir 'unreal.log') + '"'))
$Process = Start-Process -FilePath (Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe') -ArgumentList $Args -WindowStyle Hidden -PassThru
try {
    if (-not $Process.WaitForExit(120000)) { throw 'Protocol automation timed out' }
    if ($Process.ExitCode -ne 0) { throw "Protocol automation exited $($Process.ExitCode)" }
    $Result = Get-Content -LiteralPath (Join-Path $TestDir 'index.json') -Raw | ConvertFrom-Json
    if ($Result.failed -ne 0 -or ($Result.succeeded + $Result.succeededWithWarnings) -ne 1) { throw 'Expected exactly one successful protocol automation test' }
    if ((Get-FileHash -LiteralPath $Module -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ModuleHash) { throw 'UE module changed during verification' }
    [ordered]@{phase=4;passed=$true;kind='UE atomic topology protocol';module_sha256=$ModuleHash;source_files_sha256=(Get-Phase4SourceHashes $Workspace);tested_at_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $TestDir 'protocol-result.json') -Encoding utf8
    Write-Output "Protocol automation passed: $TestDir"
} finally {
    if (-not $Process.HasExited) { Stop-Process -Id $Process.Id }
}
