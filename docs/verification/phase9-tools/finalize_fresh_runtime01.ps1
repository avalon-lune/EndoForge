$ErrorActionPreference = 'Stop'
$Workspace = 'E:\Medical Image Visualization and Analysis'
Set-Location -LiteralPath $Workspace
$PythonExe = 'E:\python\python.exe'
$Work = Join-Path $Workspace 'tmp/phase9/final-runtime01'
if (Test-Path -LiteralPath $Work) { throw 'Use a fresh final runtime work directory.' }
$Extraction = Get-Content -LiteralPath 'output/Phase9/EndoForge-Phase9-review-final01-extraction.json' -Raw | ConvertFrom-Json
if ($Extraction.passed -ne $true -or $Extraction.extraction_verified -ne $true) { throw 'Actual fresh extraction has not passed.' }
New-Item -ItemType Directory -Path $Work | Out-Null
$Steps = [Collections.Generic.List[object]]::new()
function Invoke-RecordedPython([string]$Name, [string[]]$Arguments) {
    $Started = [DateTime]::UtcNow.ToString('o')
    $Log = Join-Path $Work ($Name + '.log')
    & $PythonExe -B @Arguments *> $Log
    $ActualExit = $LASTEXITCODE
    $Steps.Add([ordered]@{name=$Name;arguments=$Arguments;started_utc=$Started;completed_utc=[DateTime]::UtcNow.ToString('o');exit_code=$ActualExit;log=$Log})
    $Steps | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Work 'progress.json') -Encoding utf8
    Write-Output ($Name + ': exit ' + $ActualExit)
    if ($ActualExit -ne 0) { throw ($Name + ' failed; see ' + $Log) }
}
$Passed = $false
$Failure = $null
try {
    $CaptureStarted = [DateTime]::UtcNow.ToString('o')
    # This is a pure PowerShell script. Terminating errors, not native
    # LASTEXITCODE, determine successful return. Actual game/native exits are
    # retained separately in package-run.json and independently validated.
    & ./Scripts/TestPhase9Package.ps1 -PackageRoot (Join-Path $Workspace 'output/Phase9/_validation/FreshExtract01') -RunName 'Phase9FreshExtract-final01' -PhysicsPort 47422 *> (Join-Path $Work 'capture.log')
    $Steps.Add([ordered]@{name='fresh-package-capture';started_utc=$CaptureStarted;completed_utc=[DateTime]::UtcNow.ToString('o');powershell_returned_without_terminating_error=$true;receipt='tmp/phase9/package-tests/Phase9FreshExtract-final01/package-run.json'})
    $Steps | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Work 'progress.json') -Encoding utf8
    Write-Output 'fresh-package-capture: PowerShell completed; actual process exits are in its receipt'
    Invoke-RecordedPython 'small-audits' @('tmp/phase9/delivery-preflight01/run_package_audits.py','--capture','tmp/phase9/package-tests/Phase9FreshExtract-final01','--package','output/Phase9/_validation/FreshExtract01','--native-reference','tmp/phase9/native-qualification-final02/dual-reference-states.jsonl','--output','tmp/phase9/audits-fresh-extract-final01')
    Invoke-RecordedPython 'presented-geometry' @('tmp/phase9/run_presented_geometry_audits.py','--trace','tmp/phase9/audits-fresh-extract-final01/presented-native-trace.jsonl','--output','tmp/phase9/presented-geometry-fresh-extract-final01')
    Invoke-RecordedPython 'complete-audit-index' @('tmp/phase9/seal_complete_package_audits.py','--small-index','tmp/phase9/audits-fresh-extract-final01/audit-run.json','--contact-report','tmp/phase9/presented-geometry-fresh-extract-final01/presented-contact.json','--liver-report','tmp/phase9/presented-geometry-fresh-extract-final01/presented-liver.json','--output','tmp/phase9/audits-fresh-extract-final01/complete-audit-index.json')
    Invoke-RecordedPython 'archive-verify-after-run' @('tmp/phase9/delivery-preflight01/archive_phase9.py','verify','--candidate','output/Phase9/EndoForge-Phase9-review-final01','--archive','output/Phase9/EndoForge-Phase9-review-final01.zip','--extracted','output/Phase9/_validation/FreshExtract01','--report','output/Phase9/EndoForge-Phase9-review-final01-extracted-verify.json','--allow-runtime-outputs')
    Invoke-RecordedPython 'review-summary' @('tmp/phase9/seal_delivery_review_summary.py','--candidate','output/Phase9/EndoForge-Phase9-review-final01','--zip','output/Phase9/EndoForge-Phase9-review-final01.zip','--archive-create','output/Phase9/EndoForge-Phase9-review-final01-archive-create.json','--archive-extract','output/Phase9/EndoForge-Phase9-review-final01-extraction.json','--archive-verify','output/Phase9/EndoForge-Phase9-review-final01-extracted-verify.json','--complete-index','tmp/phase9/audits-fresh-extract-final01/complete-audit-index.json','--native-qualification','tmp/phase9/native-qualification-final02/qualification.json','--raw-holds','tmp/phase9/native-qualification-final02/long-hold-raw-state-audit.json','--native-geometry','tmp/phase9/native-geometry-final02/final-coverage-index.json','--endurance-index','tmp/phase9/endurance-geometry-final02/audit-run.json','--build-receipt','tmp/phase9/build-receipt-final01.json','--preservation','tmp/phase9/delivery-preflight01/preservation-check.json','--output','output/Phase9/phase9-review-verification-final01.json')
    $Passed = $true
} catch {
    $Failure = $_.Exception.Message
    throw
} finally {
    [ordered]@{schema='endoforge.phase9.fresh-extraction-finalization.v1';passed=$Passed;completed_utc=[DateTime]::UtcNow.ToString('o');steps=@($Steps.ToArray());error=$Failure;human_visual_approval='pending';script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Work 'execution.json') -Encoding utf8
}
