param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')][string]$RunName = ('import-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $PID),
    [string]$EngineRoot = 'E:/UE_5.7',
    [ValidateRange(60,1800)][int]$TimeoutSeconds = 600,
    [switch]$DryRun
)
# Explicit authoring import only. Build the editor separately before invoking.
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$Work = [IO.Path]::GetFullPath((Join-Path $Root ('tmp/phase9/imports/' + $RunName)))
$Editor = Join-Path ([IO.Path]::GetFullPath($EngineRoot)) 'Engine/Binaries/Win64/UnrealEditor.exe'
$Project = Join-Path $Root 'Prototype/LapTrainer/LapTrainer.uproject'
$Wrapper = Join-Path $PSScriptRoot 'ImportPhase9Assets.py'
$Log = Join-Path $Work 'ue.log'
$Arguments = @(('"' + $Project.Replace('\','/') + '"'), ('-ExecutePythonScript="' + $Wrapper.Replace('\','/') + '"'), '-unattended', '-nosplash', '-nosound', '-NoP4', '-d3d12', ('-abslog="' + $Log.Replace('\','/') + '"'))
if ($DryRun) {
    [ordered]@{phase=9;diagnostic_only=$true;executable=$Editor;arguments=$Arguments;output=$Work;report_environment='LAP_PHASE9_IMPORT_REPORT_DIR';launches_process=$false} | ConvertTo-Json -Depth 5
    return
}
if (Test-Path -LiteralPath $Work) { throw "Use a new RunName; existing import evidence is preserved: $Work" }
$Inputs = @($Editor,$Project,$Wrapper,(Join-Path $PSScriptRoot 'GeneratePhase9Assets.py'),(Join-Path $PSScriptRoot 'VerifyPhase9StaticAssets.py'),(Join-Path $Root 'Assets/Phase9/scene.json'),(Join-Path $Root 'Assets/Phase9/physics-mesh.json'))
foreach ($Path in $Inputs) { if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing import input: $Path" } }
$Phase9Destination = Join-Path $Root 'Prototype/LapTrainer/Content/Phase9'
if (Test-Path -LiteralPath $Phase9Destination) {
    foreach ($Item in @((Get-Item -LiteralPath $Phase9Destination -Force)) + @(Get-ChildItem -LiteralPath $Phase9Destination -Recurse -Force)) {
        if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Phase9 import destination must not contain a reparse point: $($Item.FullName)" }
    }
}
foreach ($ExistingEditor in @(Get-CimInstance Win32_Process -Filter "Name='UnrealEditor.exe'")) {
    if ($ExistingEditor.CommandLine -and $ExistingEditor.CommandLine.Replace('\','/').IndexOf($Project.Replace('\','/'),[StringComparison]::OrdinalIgnoreCase) -ge 0) {
        throw 'This project is already open in UnrealEditor. Close it before importing; no existing process was stopped.'
    }
}
function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-NewJson([string]$Path, $Data) {
    $Stream = [IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $Writer = [IO.StreamWriter]::new($Stream,[Text.UTF8Encoding]::new($false))
    try { $Writer.Write(($Data | ConvertTo-Json -Depth 18) + [Environment]::NewLine) } finally { $Writer.Dispose() }
}
function Get-ProtectedIdentity {
    $Identity = @{}
    $Queue = [Collections.Generic.Queue[string]]::new()
    foreach ($Folder in @('Prototype/LapTrainer/Content','Assets/Phase5','Assets/Phase6','Assets/Phase7','Assets/Phase8')) {
        $Directory = Join-Path $Root $Folder
        if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { throw "Missing protected directory: $Directory" }
        $Queue.Enqueue($Directory)
    }
    $Phase9Content = [IO.Path]::GetFullPath((Join-Path $Root 'Prototype/LapTrainer/Content/Phase9'))
    while ($Queue.Count) {
        $Directory = $Queue.Dequeue()
        if ((Get-Item -LiteralPath $Directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Protected directory is a reparse point: $Directory" }
        foreach ($Item in @(Get-ChildItem -LiteralPath $Directory -Force)) {
            if ($Item.FullName -eq $Phase9Content) { continue }
            if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Protected member is a reparse point: $($Item.FullName)" }
            if ($Item.PSIsContainer) { $Queue.Enqueue($Item.FullName) }
            else { $Identity[$Item.FullName.Substring($Root.Length+1).Replace('\','/')] = Get-Sha $Item.FullName }
        }
    }
    return $Identity
}
function Compare-Protected($Before, $After) {
    foreach ($Name in @($Before.Keys | Sort-Object)) {
        if (-not $After.ContainsKey($Name)) { 'missing: ' + $Name }
        elseif ($Before[$Name] -ne $After[$Name]) { 'changed: ' + $Name }
    }
    foreach ($Name in @($After.Keys | Sort-Object)) { if (-not $Before.ContainsKey($Name)) { 'added: ' + $Name } }
}
New-Item -ItemType Directory -Path $Work | Out-Null
$InputHashes = [ordered]@{}
foreach ($Path in $Inputs) { $InputHashes[$Path] = Get-Sha $Path }
$Before = Get-ProtectedIdentity
Write-NewJson (Join-Path $Work 'protected-before.json') ([ordered]@{schema='endoforge.phase9.import-content.v1';phase=9;stage='before';files_sha256=$Before})
$Started = [DateTime]::UtcNow
$Process = $null
$Failure = $null
$ExitCode = $null
$After = @{}
$Differences = @()
$PreviousReportDirectory = [Environment]::GetEnvironmentVariable('LAP_PHASE9_IMPORT_REPORT_DIR','Process')
try {
    [Environment]::SetEnvironmentVariable('LAP_PHASE9_IMPORT_REPORT_DIR',$Work,'Process')
    $Process = Start-Process -FilePath $Editor -ArgumentList $Arguments -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Work 'ue.stdout.log') -RedirectStandardError (Join-Path $Work 'ue.stderr.log')
    $OwnedHandle = $Process.Handle
    if (-not $Process.WaitForExit($TimeoutSeconds*1000)) { throw "Owned Phase9 import exceeded $TimeoutSeconds seconds." }
    $Process.WaitForExit()
    $Process.Refresh()
    $ExitCode = $Process.ExitCode
    if ($ExitCode -ne 0) { throw "Owned Phase9 import exited with code $ExitCode." }
} catch { $Failure = $_.Exception.Message } finally {
    [Environment]::SetEnvironmentVariable('LAP_PHASE9_IMPORT_REPORT_DIR',$PreviousReportDirectory,'Process')
    if ($Process) {
        $Process.Refresh()
        if (-not $Process.HasExited) { $Process.Kill(); $Process.WaitForExit(); $Failure = (@($Failure,'Owned importer required forced termination.') | Where-Object { $_ }) -join '; ' }
        $Process.Refresh()
        $ExitCode = $Process.ExitCode
        $Process.Dispose()
    }
    try {
        $After = Get-ProtectedIdentity
        $Differences = @(Compare-Protected $Before $After)
        Write-NewJson (Join-Path $Work 'protected-after.json') ([ordered]@{schema='endoforge.phase9.import-content.v1';phase=9;stage='after';files_sha256=$After;differences=$Differences})
        if ($Differences.Count) { throw 'Protected earlier assets or common Content changed during import.' }
        foreach ($Path in $Inputs) { if ((Get-Sha $Path) -ne $InputHashes[$Path]) { throw "Import input changed during this invocation: $Path" } }
    } catch { $Failure = (@($Failure,$_.Exception.Message) | Where-Object { $_ }) -join '; ' }
}
$ReportHashes = [ordered]@{}
$Material = $null
$Geometry = $null
$Marker = $false
try {
    foreach ($Name in @('material-import-verification.json','ue-static-asset-verification.json','static-mesh-import.json')) {
        $Path = Join-Path $Work $Name
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).LastWriteTimeUtc -lt $Started) { throw "Fresh import report missing: $Name" }
        $ReportHashes[$Name] = Get-Sha $Path
    }
    $Material = Get-Content -LiteralPath (Join-Path $Work 'material-import-verification.json') -Raw | ConvertFrom-Json
    $Geometry = Get-Content -LiteralPath (Join-Path $Work 'ue-static-asset-verification.json') -Raw | ConvertFrom-Json
    if ($Material.schema -ne 'endoforge.phase9.material-import.v1' -or $Material.passed -ne $true -or @($Material.materials).Count -ne 3 -or @($Material.materials | Where-Object { $_.compiled_instructions_available -ne $true -or -not $_.asset.StartsWith('/Game/Phase9/Materials/') }).Count) { throw 'Phase9 compiled material statistics missing or failed.' }
    if ($Geometry.schema -ne 'endoforge.phase9.ue-static-assets.v1' -or $Geometry.passed -ne $true -or @($Geometry.objects).Count -eq 0 -or @($Geometry.objects | Where-Object { $_.passed -ne $true }).Count) { throw 'Actual Phase9 imported-buffer checks missing or failed.' }
    $Marker = (Test-Path -LiteralPath $Log) -and (Select-String -LiteralPath $Log -SimpleMatch 'PHASE9_IMPORT_AND_VERIFY_PASS' -Quiet)
    if (-not $Marker) { throw 'Scoped Phase9 import completion marker missing.' }
} catch { $Failure = (@($Failure,$_.Exception.Message) | Where-Object { $_ }) -join '; ' }
$Receipt = Join-Path $Work 'import-receipt.json'
Write-NewJson $Receipt ([ordered]@{
    schema='endoforge.phase9.editor-import-diagnostic.v1';phase=9;diagnostic_only=$true
    import_checks_passed=(-not $Failure -and $ExitCode -eq 0 -and $Marker);run_name=$RunName
    started_utc=$Started.ToString('o');duration_s=([DateTime]::UtcNow-$Started).TotalSeconds;exit_code=$ExitCode
    editor=$Editor;arguments=$Arguments;error=$Failure;inputs_sha256=$InputHashes;reports_sha256=$ReportHashes
    protected_files_count=$Before.Count;protected_assets_unchanged=($Before.Count -eq $After.Count -and $Differences.Count -eq 0);protected_differences=$Differences
    scope='Phase9 authoring import and actual imported-buffer diagnostics only. Fresh shader-map, physical geometry, runtime, visual and package qualification remain separate.'
})
Write-Output ('PHASE9_IMPORT_RECEIPT=' + $Receipt)
if ($Failure) { throw "Phase9 import diagnostics failed: $Failure Evidence: $Work" }
