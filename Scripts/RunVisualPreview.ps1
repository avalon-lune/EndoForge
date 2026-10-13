param([string]$RunName = ('phase2-visual-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
$TestRoot = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$PreviewDir = [IO.Path]::GetFullPath((Join-Path $TestRoot $RunName))
if (-not $PreviewDir.StartsWith($TestRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid preview destination' }
if (Test-Path -LiteralPath $PreviewDir) { throw 'Use a fresh preview directory.' }
New-Item -ItemType Directory -Path $PreviewDir -Force | Out-Null
$ProjectPath = Join-Path $Workspace 'Prototype/LapTrainer/LapTrainer.uproject'
$PreviewArgs = @(('"' + $ProjectPath + '"'), '-game', '-windowed', '-ResX=1600', '-ResY=900', '-d3d11', '-nosound', '-unattended', '-LapVisualPreview', '-LapAutoExit', ('-LapCaptureDir="' + $PreviewDir + '"'), ('-abslog="' + (Join-Path $PreviewDir 'unreal.log') + '"'), '-ExecCmds="t.MaxFPS 60"')
$PreviewProcess = Start-Process -FilePath 'E:/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' -ArgumentList $PreviewArgs -WindowStyle Hidden -PassThru
try {
    if (-not $PreviewProcess.WaitForExit(90000)) { throw 'Visual preview timed out.' }
    if ($PreviewProcess.ExitCode -ne 0) { throw "Visual preview exited $($PreviewProcess.ExitCode)" }
    Get-ChildItem -LiteralPath $PreviewDir -Filter '*.png' | Select-Object Name, Length
}
finally {
    if (-not $PreviewProcess.HasExited) { Stop-Process -Id $PreviewProcess.Id -ErrorAction SilentlyContinue }
}
