param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$Runtime = Join-Path $PSScriptRoot 'runtime'
$Exe = Join-Path $Runtime 'LapPhysics.exe'
$BuildInfoPath = Join-Path $Runtime 'build-info.json'
$PhysicsReportPath = Join-Path $Runtime 'phase3-physics-test-results.json'
$NetworkReportPath = Join-Path $Runtime 'phase3-network-test-results.json'
function Assert-PortFree {
    $Listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if (@($Listeners | Where-Object Port -eq 47324).Count -gt 0) {
        throw 'Port 47324 is in use. Close your Phase 3 service before regression; no existing process was stopped.'
    }
}
function Get-ExeHash { (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-SameBinary([string]$Expected) {
    if ((Get-ExeHash) -ne $Expected) { throw 'LapPhysics.exe changed during regression. These reports do not verify a single binary.' }
}
foreach ($Required in @($Exe,$BuildInfoPath)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing $Required. Run download-dependencies.ps1 and build.ps1 first." }
}
Get-Command $Python -ErrorAction Stop | Out-Null
& $Python -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required for the network test.' }
Assert-PortFree
$ExeHash = Get-ExeHash
$BuildInfo = Get-Content -LiteralPath $BuildInfoPath -Raw | ConvertFrom-Json
if ($BuildInfo.executable_sha256 -ne $ExeHash) { throw 'Build metadata differs from the executable; rebuild/stage before regression.' }
foreach ($Entry in $BuildInfo.source_files_sha256.PSObject.Properties) {
    $Actual = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $Entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Entry.Value) { throw "Source $($Entry.Name) differs from staged build metadata. Rebuild/stage first." }
}
$Started = [DateTime]::UtcNow
$TemporaryReport = Join-Path $Runtime ('phase3-selftest-' + [guid]::NewGuid().ToString('N') + '.json')
& $Exe --self-test-phase3 $TemporaryReport
$NumericalExit = $LASTEXITCODE
Assert-SameBinary $ExeHash
if (-not (Test-Path -LiteralPath $TemporaryReport -PathType Leaf)) { throw 'Native numerical test did not produce a report.' }
$Report = Get-Content -LiteralPath $TemporaryReport -Raw | ConvertFrom-Json
$Report | Add-Member -NotePropertyName executable_sha256 -NotePropertyValue $ExeHash -Force
$Report | Add-Member -NotePropertyName tested_at_utc -NotePropertyValue $Started.ToString('o') -Force
$Report | Add-Member -NotePropertyName native_exit_code -NotePropertyValue $NumericalExit -Force
$Report | Add-Member -NotePropertyName source_files_sha256 -NotePropertyValue $BuildInfo.source_files_sha256 -Force
# The native report retains its nominal integration step for compatibility.
# Spell out the retry policy implemented by this build so it cannot be read as
# a claim that every accepted animation used one fixed 1/30-second substep.
$Report.model | Add-Member -NotePropertyName physics_substep_s_is_nominal -NotePropertyValue $true -Force
$Report.model | Add-Member -NotePropertyName physics_substep_min_s -NotePropertyValue (1.0/120) -Force
$Report.model | Add-Member -NotePropertyName physics_substep_max_s -NotePropertyValue (1.0/30) -Force
$Report.model | Add-Member -NotePropertyName adaptive_substep_counts -NotePropertyValue @(1,2,4) -Force
$Report | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $PhysicsReportPath -Encoding UTF8
Remove-Item -LiteralPath $TemporaryReport -Force
if ($NumericalExit -ne 0 -or $Report.phase -ne 3 -or $Report.passed -ne $true -or $Report.experimental -eq $true) {
    throw "Numerical regression failed; see $PhysicsReportPath"
}
Assert-PortFree
if (Test-Path -LiteralPath $NetworkReportPath) {
    Move-Item -LiteralPath $NetworkReportPath -Destination (Join-Path $Runtime 'phase3-network-test-results.previous.json') -Force
}
& $Python (Join-Path $PSScriptRoot 'test_phase3_network.py')
$NetworkExit = $LASTEXITCODE
Assert-SameBinary $ExeHash
if (-not (Test-Path -LiteralPath $NetworkReportPath -PathType Leaf)) { throw 'Network test did not produce a fresh report.' }
$NetworkReport = Get-Content -LiteralPath $NetworkReportPath -Raw | ConvertFrom-Json
if ($NetworkExit -ne 0 -or $NetworkReport.phase -ne 3 -or $NetworkReport.passed -ne $true -or $NetworkReport.experimental -eq $true -or $NetworkReport.executable_sha256 -ne $ExeHash) {
    throw "Network regression failed; see $NetworkReportPath"
}
$BuildInfo | Add-Member -NotePropertyName tested_protocol -NotePropertyValue 3 -Force
$BuildInfo | Add-Member -NotePropertyName verification_status -NotePropertyValue 'native numerical and real TCP tests passed' -Force
$BuildInfo | Add-Member -NotePropertyName verified_at_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$BuildInfo | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $BuildInfoPath -Encoding UTF8
Write-Host "Phase 3 numerical and network regression passed for $ExeHash"
