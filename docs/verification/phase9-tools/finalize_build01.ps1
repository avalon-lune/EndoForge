$ErrorActionPreference = 'Stop'
$Root = 'E:/Medical Image Visualization and Analysis'
Set-Location -LiteralPath $Root
$Qualification = Join-Path $Root 'tmp/phase9/native-qualification-final02/qualification.json'
$Deadline = [DateTime]::UtcNow.AddMinutes(75)
while (-not (Test-Path -LiteralPath $Qualification)) {
    if ([DateTime]::UtcNow -gt $Deadline) { throw 'Timed out waiting for actual fresh qualification; no final staging ran.' }
    Start-Sleep -Seconds 10
}
$Evidence = Get-Content -LiteralPath $Qualification -Raw | ConvertFrom-Json
if ($Evidence.passed -ne $true -or $Evidence.case_count -ne 35) { throw 'Fresh native35 failed; no final staging ran.' }
$Before = (Get-FileHash -LiteralPath 'Physics/runtime/LapPhysics.exe' -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Before -ne $Evidence.native_binary.sha256) { throw 'Executable changed before final staging.' }
Write-Output 'Fresh native35 passed; starting final no-op native compile and staging.'
& './Physics/build.ps1' *> 'tmp/phase9/native-build-final02.log'
if ($LASTEXITCODE -ne 0) { throw 'Final native build/stage failed.' }
$After = (Get-FileHash -LiteralPath 'Physics/runtime/LapPhysics.exe' -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Before -ne $After) { throw 'Final staging changed the qualified executable.' }
& 'E:/python/python.exe' -B 'Scripts/Phase9/write_build_receipt.py' seal --prepared 'tmp/phase9/build-inputs-final01.json' --ue-package 'tmp/phase9/ue-archive-final01/Windows' --native-runtime 'Physics/runtime' --assets 'Assets/Phase9' --native-build-log 'tmp/phase9/native-build-final02.log' --native-exit-code 0 --editor-build-log 'tmp/phase9/ue-editor-build-final01.log' --editor-exit-code 0 --package-log 'tmp/phase9/ue-package-final01.log' --package-exit-code 0 --output 'tmp/phase9/build-receipt-final01.json'
if ($LASTEXITCODE -ne 0) { throw 'Final build receipt could not be sealed.' }
Write-Output 'Successful final build receipt sealed; human approval remains pending.'
