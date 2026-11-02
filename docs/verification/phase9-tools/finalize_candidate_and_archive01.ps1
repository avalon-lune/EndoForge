$ErrorActionPreference = 'Stop'
$Workspace = 'E:\Medical Image Visualization and Analysis'
Set-Location -LiteralPath $Workspace
$PythonExe = 'E:\python\python.exe'
$Work = Join-Path $Workspace 'tmp/phase9/final-assembly01'
if (Test-Path -LiteralPath $Work) { throw 'Use a fresh final assembly work directory.' }
$NativeIndex = Get-Content -LiteralPath 'tmp/phase9/native-geometry-final02/final-coverage-index.json' -Raw | ConvertFrom-Json
$EnduranceIndex = Get-Content -LiteralPath 'tmp/phase9/endurance-geometry-final02/audit-run.json' -Raw | ConvertFrom-Json
if ($NativeIndex.passed -ne $true -or $EnduranceIndex.passed -ne $true) { throw 'Actual complete geometry prerequisites have not passed.' }
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
    Invoke-RecordedPython 'validation' @('tmp/phase9/prepare_validation_receipt01.py','--output','tmp/phase9/validation-final01.json','--build-receipt','tmp/phase9/build-receipt-final01.json','--endurance-audit-index','tmp/phase9/endurance-geometry-final02/audit-run.json','--package-audit-index','tmp/phase9/audits-package-final01/complete-audit-index.json')
    Invoke-RecordedPython 'assembly' @('Scripts/Phase9/assemble_review_candidate.py','--ue-package','tmp/phase9/ue-archive-final01/Windows','--native-runtime','Physics/runtime','--assets','Assets/Phase9','--output','output/Phase9/EndoForge-Phase9-review-final01','--validation-receipt','tmp/phase9/validation-final01.json')
    Invoke-RecordedPython 'archive-create' @('tmp/phase9/delivery-preflight01/archive_phase9.py','create','--candidate','output/Phase9/EndoForge-Phase9-review-final01','--archive','output/Phase9/EndoForge-Phase9-review-final01.zip','--report','output/Phase9/EndoForge-Phase9-review-final01-archive-create.json','--allow-runtime-outputs')
    Invoke-RecordedPython 'archive-extract' @('tmp/phase9/delivery-preflight01/archive_phase9.py','extract','--candidate','output/Phase9/EndoForge-Phase9-review-final01','--archive','output/Phase9/EndoForge-Phase9-review-final01.zip','--extracted','output/Phase9/_validation/FreshExtract01','--report','output/Phase9/EndoForge-Phase9-review-final01-extraction.json')
    $Passed = $true
} catch {
    $Failure = $_.Exception.Message
    throw
} finally {
    [ordered]@{schema='endoforge.phase9.final-assembly-execution.v1';passed=$Passed;completed_utc=[DateTime]::UtcNow.ToString('o');steps=@($Steps.ToArray());error=$Failure;human_visual_approval='pending';fresh_extraction_runtime_test_performed=$false;script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Work 'execution.json') -Encoding utf8
}
