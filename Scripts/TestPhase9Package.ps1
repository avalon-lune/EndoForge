param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')][string]$RunName = ('Phase9PackageAcceptance-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $PID),
    [ValidateRange(1025,65535)][int]$PhysicsPort = 47421,
    [ValidateRange(30,1200)][int]$TimeoutSeconds = 780,
    [switch]$DryRun
)
# Direct packaged equivalent of Prototype/LapTrainer/Scripts/TestPhase9Editor.ps1.
# Captures four internal validation frames. It does not build, inherit native
# qualification, approve appearance, or accept a final delivery.
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$AllowedPackageRoot = [IO.Path]::GetFullPath((Join-Path $Root 'output/Phase9'))
if (-not $PackageRoot.StartsWith($AllowedPackageRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Package must be a Phase9 candidate or fresh extraction under output/Phase9.' }
$Runs = [IO.Path]::GetFullPath((Join-Path $Root 'tmp/phase9/package-tests'))
$Run = [IO.Path]::GetFullPath((Join-Path $Runs $RunName))
if (-not $Run.StartsWith($Runs+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'RunName must remain within tmp/phase9/package-tests.' }
if (Test-Path -LiteralPath $Run) { throw "Use a fresh RunName to preserve evidence: $Run" }
$Physics = Join-Path $PackageRoot 'Physics/LapPhysics.exe'
$GameExecutable = Join-Path $PackageRoot 'LapTrainer/Binaries/Win64/LapTrainer.exe'
$Anatomy = Join-Path $PackageRoot 'Assets/Phase9'
$ManifestFile = Join-Path $PackageRoot 'assembly-manifest.json'
$CandidateFile = Join-Path $PackageRoot 'review-candidate.json'
$Session = Join-Path $Run 'native-session'
$NativeArguments = @('--phase6','--mesh',('"'+(Join-Path $Anatomy 'physics-mesh.json')+'"'),'--port',"$PhysicsPort",'--session-dir',('"'+$Session+'"'),'--exit-after-client')
$GameArguments = @('-LapPhase9','-LapPhase9Test','-d3d12','-LapAutoExit',('-LapPhysicsPort='+$PhysicsPort),('-LapAnatomyDir="'+$Anatomy+'"'),('-LapCaptureDir="'+$Run+'"'),'-windowed','-ResX=1920','-ResY=1080','-NoVSync','-nosplash','-nosound','-unattended',('-abslog="'+(Join-Path $Run 'ue.log')+'"'))
if ($DryRun) {
    [ordered]@{phase=9;run_kind='acceptance_test';native_executable=$Physics;native_arguments=$NativeArguments;game_executable=$GameExecutable;game_arguments=$GameArguments;port=$PhysicsPort;output=$Run;launches_process=$false;scope='Packaged integration capture only; separate new native qualification, independent audits and human review remain required.'} | ConvertTo-Json -Depth 5
    return
}
function Assert-NoReparsePath([string]$Path) {
    $Item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    while ($null -ne $Item) {
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Links and reparse points are forbidden: $($Item.FullName)" }
        if ($Item -is [IO.FileInfo]) { $Item = $Item.Directory } else { $Item = $Item.Parent }
    }
}
function Resolve-PackageMember([string]$Name) {
    if (-not $Name -or $Name.Contains('\') -or $Name.Contains(':') -or $Name.StartsWith('/') -or @($Name.Split('/') | Where-Object { $_ -in @('','.','..') }).Count) { throw "Invalid manifest member: $Name" }
    $Path = [IO.Path]::GetFullPath((Join-Path $PackageRoot $Name))
    if (-not $Path.StartsWith($PackageRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw "Manifest member escapes the package: $Name" }
    Assert-NoReparsePath $Path
    return $Path
}
foreach ($Path in @($Physics,$GameExecutable,(Join-Path $Anatomy 'scene.json'),(Join-Path $Anatomy 'physics-mesh.json'),$ManifestFile,$CandidateFile)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required package-capture input missing: $Path" }
    Assert-NoReparsePath $Path
}
$ManifestHash = (Get-FileHash -LiteralPath $ManifestFile -Algorithm SHA256).Hash.ToLowerInvariant()
$Manifest = @(Get-Content -LiteralPath $ManifestFile -Raw | ConvertFrom-Json)
function Assert-PackageManifest {
    if (-not $Manifest.Count) { throw 'An explicit nonempty assembly manifest is required.' }
    $Expected = @{}
    foreach ($Entry in $Manifest) {
        if ($Expected.ContainsKey($Entry.path.ToLowerInvariant()) -or $Entry.path -eq 'assembly-manifest.json' -or $Entry.sha256 -notmatch '^[0-9a-f]{64}$' -or $Entry.bytes -lt 0) { throw 'Invalid or duplicate assembly manifest row.' }
        $Path = Resolve-PackageMember $Entry.path
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).Length -ne $Entry.bytes -or (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) { throw "Assembly manifest mismatch: $($Entry.path)" }
        $Expected[$Entry.path.ToLowerInvariant()] = $true
    }
    $Actual = @{}
    foreach ($Item in @(Get-ChildItem -LiteralPath $PackageRoot -Recurse -Force)) {
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Package contains a link or reparse point: $($Item.FullName)" }
        if ($Item.PSIsContainer) { continue }
        $Relative = $Item.FullName.Substring($PackageRoot.Length+1).Replace('\','/')
        $Parts = $Relative.Split('/')
        if ($Relative -eq 'assembly-manifest.json' -or @($Parts | Where-Object { $_.ToLowerInvariant() -in @('saved','logs','sessions') }).Count) { continue }
        $Actual[$Relative.ToLowerInvariant()] = $true
    }
    if ($Actual.Count -ne $Expected.Count -or @($Actual.Keys | Where-Object { -not $Expected.ContainsKey($_) }).Count) { throw 'Package membership differs from the explicit assembly manifest.' }
    if ((Get-FileHash -LiteralPath $ManifestFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestHash) { throw 'Assembly manifest changed.' }
}
Assert-PackageManifest
$Candidate = Get-Content -LiteralPath $CandidateFile -Raw | ConvertFrom-Json
if ($Candidate.schema -ne 'endoforge.phase9.review-candidate.v1' -or $Candidate.phase -ne 9 -or $Candidate.candidate_status -ne 'review_candidate' -or $Candidate.delivery_accepted -ne $false -or $Candidate.human_visual_approval -notin @('pending','approved')) { throw 'Expected an explicit Phase9 review candidate, without a final delivery claim.' }
$QualificationPath = Resolve-PackageMember $Candidate.provided_evidence.native_qualification.package_path
if ((Get-FileHash -LiteralPath $QualificationPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Candidate.provided_evidence.native_qualification.sha256) { throw 'Packaged current qualification hash mismatch.' }
$Qualification = Get-Content -LiteralPath $QualificationPath -Raw | ConvertFrom-Json
if ($Qualification.schema -ne 'endoforge.phase9.native-qualification.v1' -or $Qualification.phase -ne 9 -or $Qualification.passed -ne $true -or $Qualification.native_execution_started -ne $true -or $Qualification.inherited_results -ne $false -or $Qualification.diagnostic_only -eq $true -or $Qualification.case_count -ne 35 -or $Qualification.expected_case_count -ne 35) { throw 'A fresh current 35-case native qualification is required; no inherited or diagnostic-only pass.' }
if (@($Qualification.checks.PSObject.Properties).Count -eq 0 -or @($Qualification.checks.PSObject.Properties | Where-Object { $_.Value -isnot [bool] -or $_.Value -ne $true }).Count) { throw 'Fresh native qualification contains missing or failed checks.' }
. (Join-Path $PackageRoot 'Phase9ProcessPolicy.ps1')
$InputPaths = [ordered]@{scene=(Join-Path $Anatomy 'scene.json');physics_mesh=(Join-Path $Anatomy 'physics-mesh.json');native_executable=$Physics;game_executable=$GameExecutable;candidate_receipt=$CandidateFile;assembly_manifest=$ManifestFile}
$InputHashes = [ordered]@{}
foreach ($Name in $InputPaths.Keys) { $InputHashes[$Name] = (Get-FileHash -LiteralPath $InputPaths[$Name] -Algorithm SHA256).Hash.ToLowerInvariant() }
if ($InputHashes.native_executable -ne $Candidate.validated_inputs.physics_exe_sha256 -or $InputHashes.physics_mesh -ne $Candidate.validated_inputs.physics_mesh_sha256 -or $InputHashes.game_executable -ne $Candidate.validated_inputs.game_exe_sha256 -or $Qualification.native_binary.sha256 -ne $InputHashes.native_executable -or $Qualification.mesh.sha256 -ne $InputHashes.physics_mesh) { throw 'Selected package binary/mesh identity differs from its supplied validation and new qualification.' }
if (Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue) { throw "Port $PhysicsPort is occupied; no existing service will be used or stopped." }
New-Item -ItemType Directory -Path $Run | Out-Null
$Native = $null
$Game = $null
$Failure = $null
$NativeGraceful = $false
$GameExit = $null
$NativeExit = $null
$Started = [DateTime]::UtcNow
try {
    $Native = Start-Process -FilePath $Physics -ArgumentList $NativeArguments -WorkingDirectory (Join-Path $PackageRoot 'Physics') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Run 'native.stdout.log') -RedirectStandardError (Join-Path $Run 'native.stderr.log')
    $NativeHandle = $Native.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Native -ExpectedExecutable $Physics -CreatedAfterUtc $Started -Receipt (Join-Path $Run 'native-timer-policy.json') | Out-Null
    $Native.Id | Set-Content -LiteralPath (Join-Path $Run 'native.pid')
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    $Listening = $false
    do {
        $Native.Refresh()
        if ($Native.HasExited) { throw "Owned native process exited before listening: $($Native.ExitCode)" }
        $Owners = @(Get-NetTCPConnection -LocalPort $PhysicsPort -State Listen -ErrorAction SilentlyContinue)
        if (@($Owners | Where-Object OwningProcess -ne $Native.Id).Count) { throw 'Another process acquired the requested native port.' }
        $Listening = @($Owners | Where-Object OwningProcess -eq $Native.Id).Count -ge 1
        if (-not $Listening) { Start-Sleep -Milliseconds 150 }
    } until ($Listening -or [DateTime]::UtcNow -ge $Deadline)
    if (-not $Listening) { throw 'Owned native process did not listen within thirty seconds.' }
    $Game = Start-Process -FilePath $GameExecutable -ArgumentList $GameArguments -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru
    $GameHandle = $Game.Handle
    Set-EndoForgeOwnedTimerPolicy -Process $Game -ExpectedExecutable $GameExecutable -CreatedAfterUtc $Started -Receipt (Join-Path $Run 'ue-timer-policy.json') | Out-Null
    $Game.Id | Set-Content -LiteralPath (Join-Path $Run 'ue.pid')
    if (-not $Game.WaitForExit($TimeoutSeconds*1000)) { throw "Owned packaged capture exceeded $TimeoutSeconds seconds." }
    $Game.WaitForExit()
    $Game.Refresh()
    $GameExit = $Game.ExitCode
    if ($GameExit -ne 0) { throw "Owned packaged capture exited with code $GameExit." }
} catch { $Failure = $_.Exception.Message+' at '+$_.ScriptStackTrace } finally {
    if ($Game) {
        $Game.Refresh()
        if (-not $Game.HasExited) { $Game.Kill(); $Game.WaitForExit(); $Failure = (@($Failure,'Owned packaged game required forced termination.') | Where-Object { $_ }) -join '; ' }
        $Game.Dispose()
    }
    if ($Native) {
        if ($Native.WaitForExit(15000)) { $Native.WaitForExit(); $Native.Refresh(); $NativeExit=$Native.ExitCode; $NativeGraceful=$NativeExit -eq 0 }
        else { $Native.Kill(); $Native.WaitForExit(); $Failure = (@($Failure,'Owned native process failed to flush and exit within fifteen seconds.') | Where-Object { $_ }) -join '; ' }
        if (-not $NativeGraceful -and -not $Failure) { $Failure = "Native service exited with code $NativeExit." }
        $Native.Dispose()
    }
}
$AfterHashes = [ordered]@{}
foreach ($Name in $InputPaths.Keys) {
    if (Test-Path -LiteralPath $InputPaths[$Name] -PathType Leaf) { $AfterHashes[$Name] = (Get-FileHash -LiteralPath $InputPaths[$Name] -Algorithm SHA256).Hash.ToLowerInvariant() }
    else { $AfterHashes[$Name] = $null }
    if ($AfterHashes[$Name] -ne $InputHashes[$Name]) { $Failure = (@($Failure,('Package-capture input changed: '+$Name)) | Where-Object { $_ }) -join '; ' }
}
$Reports = [ordered]@{}
$ReportHashes = [ordered]@{}
$FrameCount = 0
try {
    Assert-PackageManifest
    foreach ($Name in @('phase5-input-test.json','phase6-interaction-test.json','phase6-runtime.json')) {
        $Path = Join-Path $Run $Name
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).LastWriteTimeUtc -lt $Started) { throw "Fresh package report missing: $Name" }
        $Reports[$Name] = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        $ReportHashes[$Name] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Reports[$Name].phase -ne 9 -or $Reports[$Name].mechanics_phase -ne 6) { throw "Wrong phase identity: $Name" }
    }
    if ($Reports['phase5-input-test.json'].passed -ne $true -or $Reports['phase5-input-test.json'].stereo_frames -ne 4) { throw 'Input checks failed or the four internal alignment frames are incomplete.' }
    if ($Reports['phase6-interaction-test.json'].passed -ne $true) { throw 'Packaged interaction checks failed.' }
    foreach ($Name in @('phase5-input-test.json','phase6-interaction-test.json')) {
        if (@($Reports[$Name].checks.PSObject.Properties).Count -eq 0 -or @($Reports[$Name].checks.PSObject.Properties | Where-Object { $_.Value -isnot [bool] -or $_.Value -ne $true }).Count) { throw "Missing or failed explicit input checks: $Name" }
    }
    if ($Reports['phase6-interaction-test.json'].schema -ne 'endoforge.phase9.interaction.v1' -or $Reports['phase6-runtime.json'].schema -ne 'endoforge.phase9.runtime.v1' -or $Reports['phase6-runtime.json'].run_kind -ne 'acceptance_test') { throw 'Packaged capture has the wrong runtime/interaction identity.' }
    if ($Reports['phase6-runtime.json'].appearance.diagnostic_neutral_grey -ne $false) { throw 'Diagnostic grey overrides cannot be used for acceptance capture.' }
    $FrameCount = @(Get-ChildItem -LiteralPath (Join-Path $Run 'dataset') -Filter 'frame.json' -Recurse -File).Count
    if ($FrameCount -ne 4) { throw 'Exactly four internal frozen-state validation frames are required.' }
} catch { $Failure = (@($Failure,$_.Exception.Message) | Where-Object { $_ }) -join '; ' }
$Receipt = [ordered]@{schema='endoforge.phase9.package-run.v1';phase=9;run_kind='acceptance_test';integration_capture_completed=(-not $Failure);package_root=$PackageRoot;port=$PhysicsPort;native_arguments=$NativeArguments;game_arguments=$GameArguments;inputs=$InputPaths;inputs_sha256=$InputHashes;inputs_after_sha256=$AfterHashes;reports_sha256=$ReportHashes;assembly_manifest_sha256=$ManifestHash;game_exit_code=$GameExit;native_exit_code=$NativeExit;native_graceful_exit=$NativeGraceful;native_session=$Session;stereo_frames=$FrameCount;duration_s=([DateTime]::UtcNow-$Started).TotalSeconds;error=$Failure;human_visual_approval=$Candidate.human_visual_approval;delivery_accepted=$false;scope='Fresh packaged integration capture only, bound to the explicit review candidate and source manifest. New native qualification is separately required and checked, not inherited. Independent data/geometry/runtime audits, human visual review and final delivery remain separate.'}
$Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Run 'package-run.json') -Encoding utf8
Write-Output ('PHASE9_PACKAGE_CAPTURE=' + $Run)
if ($Failure) { throw "$Failure Evidence: $Run" }
