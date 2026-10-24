param([string]$Python = 'python', [switch]$SkipLegacy)
$ErrorActionPreference = 'Stop'
$Runtime = Join-Path $PSScriptRoot 'runtime'
$Exe = Join-Path $Runtime 'LapPhysics.exe'
$BuildInfoPath = Join-Path $Runtime 'build-info.json'
$BuildInfo = Get-Content -LiteralPath $BuildInfoPath -Raw | ConvertFrom-Json
$ExeHash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($BuildInfo.executable_sha256 -ne $ExeHash) { throw 'Executable differs from staged metadata.' }
foreach ($Entry in $BuildInfo.source_files_sha256.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $Entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.Value) { throw "Source changed after staging: $($Entry.Name)" }
}
$Started = [DateTime]::UtcNow
$Jobs = @()
try {
    foreach ($Name in @('core','flat','curved')) {
        $ReportName = if ($Name -eq 'core') { 'phase4-physics-test-results.json' } else { "phase4-endurance-$Name.json" }
        $Report = Join-Path $Runtime $ReportName
        $Arguments = if ($Name -eq 'core') { @('--self-test-phase4', ('"' + $Report + '"')) } else { @('--endurance-phase4',$Name,'--duration','600','--report',('"' + $Report + '"')) }
        $Process = Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $Runtime -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Runtime "phase4-$Name-test.log") -RedirectStandardError (Join-Path $Runtime "phase4-$Name-test.err.log") -PassThru
        $Jobs += [pscustomobject]@{ Name=$Name; Process=$Process; Report=$Report }
    }
    $Deadline = [DateTime]::UtcNow.AddHours(1)
    $NextUpdate = [DateTime]::UtcNow
    while (@($Jobs | Where-Object { -not $_.Process.HasExited }).Count -gt 0) {
        if ([DateTime]::UtcNow -gt $Deadline) { throw 'Native Phase 4 regression timed out after one hour.' }
        if ([DateTime]::UtcNow -ge $NextUpdate) {
            Write-Host ('Native tests running: ' + (($Jobs | Where-Object { -not $_.Process.HasExited } | ForEach-Object Name) -join ', '))
            $NextUpdate = [DateTime]::UtcNow.AddSeconds(30)
        }
        Start-Sleep -Milliseconds 500
    }
    $Passed = $true
    foreach ($Job in $Jobs) {
        $Job.Process.WaitForExit()
        if (-not (Test-Path -LiteralPath $Job.Report) -or (Get-Item -LiteralPath $Job.Report).LastWriteTimeUtc -lt $Started) { throw "No fresh report for $($Job.Name)" }
        $Report = Get-Content -LiteralPath $Job.Report -Raw | ConvertFrom-Json
        $Report | Add-Member -NotePropertyName executable_sha256 -NotePropertyValue $ExeHash -Force
        $Report | Add-Member -NotePropertyName source_files_sha256 -NotePropertyValue $BuildInfo.source_files_sha256 -Force
        $Report | Add-Member -NotePropertyName tested_at_utc -NotePropertyValue $Started.ToString('o') -Force
        $Report | Add-Member -NotePropertyName native_exit_code -NotePropertyValue $Job.Process.ExitCode -Force
        $Report | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $Job.Report -Encoding UTF8
        $Passed = $Passed -and $Report.passed -and ($Job.Process.ExitCode -eq 0)
    }
    if ((Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExeHash) { throw 'Executable changed while regression ran.' }
    if (-not $Passed) { throw 'Native Phase 4 acceptance failed; inspect the three reports.' }
    & $Python (Join-Path $PSScriptRoot 'test_phase4_network.py')
    if ($LASTEXITCODE -ne 0) { throw 'Protocol 4 TCP session acceptance failed.' }
    $NetworkPath = Join-Path $Runtime 'phase4-network-test-results.json'
    $Network = Get-Content -LiteralPath $NetworkPath -Raw | ConvertFrom-Json
    if (-not $Network.passed -or $Network.executable_sha256 -ne $ExeHash) { throw 'Network report provenance mismatch.' }
    $Network | Add-Member -NotePropertyName source_files_sha256 -NotePropertyValue $BuildInfo.source_files_sha256 -Force
    $Network | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $NetworkPath -Encoding UTF8
    if (-not $SkipLegacy) {
        & (Join-Path $PSScriptRoot 'RunPhase3Regression.ps1') -Python $Python
        if ($LASTEXITCODE -ne 0) { throw 'Legacy Phase 3 regression failed.' }
    }
    $BuildInfo | Add-Member -NotePropertyName tested_protocol -NotePropertyValue 4 -Force
    $BuildInfo | Add-Member -NotePropertyName tested_protocols -NotePropertyValue $(if ($SkipLegacy) { @(4) } else { @(3,4) }) -Force
    $BuildInfo | Add-Member -NotePropertyName verification_status -NotePropertyValue 'Phase 4 native core, replay, 600s flat/curved endurance, persisted TCP replay passed' -Force
    $BuildInfo | Add-Member -NotePropertyName verified_at_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    $BuildInfo | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $BuildInfoPath -Encoding UTF8
    Write-Host "Phase 4 acceptance passed for $ExeHash"
} finally {
    foreach ($Job in $Jobs) { if (-not $Job.Process.HasExited) { Stop-Process -Id $Job.Process.Id -ErrorAction SilentlyContinue } }
}
