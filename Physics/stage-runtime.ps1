$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$sdk = Join-Path $project 'ThirdParty/SOFA/sdk/SOFA_v26.06.00_Win64'
$runtime = Join-Path $PSScriptRoot 'runtime'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) {
    $vswhereCommand = Get-Command 'vswhere.exe' -ErrorAction SilentlyContinue
    if ($vswhereCommand) { $vswhere = $vswhereCommand.Source }
    else { throw 'vswhere.exe was not found. Install Visual Studio 2022 with Desktop development with C++ before staging the physics runtime.' }
}
$vsInstall = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $vsInstall) {
    throw 'No Visual Studio installation containing the x64 C++ build tools was found by vswhere.'
}
$toolsetRoot = Join-Path ($vsInstall | Select-Object -First 1) 'VC/Tools/MSVC'
$dumpbinCandidate = Get-ChildItem -LiteralPath $toolsetRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } |
    Sort-Object { [version]$_.Name } -Descending |
    ForEach-Object { Join-Path $_.FullName 'bin/Hostx64/x64/dumpbin.exe' } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $dumpbinCandidate) {
    throw "No x64 dumpbin.exe was found under $toolsetRoot. Install an MSVC x64 toolset using Visual Studio Installer."
}
$dumpbin = $dumpbinCandidate
$queue = [System.Collections.Generic.Queue[string]]::new()
$queue.Enqueue((Join-Path $runtime 'LapPhysics.exe'))
$plugins = @('AnimationLoop','StateContainer','Topology.Container.Dynamic','Topology.Container.Constant','ODESolver.Backward','LinearSolver.Iterative','LinearSolver.Direct','Mass','MechanicalLoad','SolidMechanics.FEM.Elastic','SolidMechanics.Spring','Constraint.Projective','Constraint.Lagrangian.Solver','Constraint.Lagrangian.Model','Constraint.Lagrangian.Correction','Collision.Detection.Algorithm','Collision.Detection.Intersection','Collision.Geometry','Collision.Response.Contact','Mapping.Linear','Mapping.NonLinear')
foreach ($name in $plugins) { $queue.Enqueue((Join-Path $sdk "bin/Sofa.Component.$name.dll")) }
$seen = @{}
while ($queue.Count -gt 0) {
    $path = $queue.Dequeue()
    $name = Split-Path -Leaf $path
    if ($seen.ContainsKey($name)) { continue }
    $seen[$name] = $true
    if ((Split-Path -Parent $path) -ne $runtime) { Copy-Item -LiteralPath $path -Destination $runtime -Force }
    $lines = & $dumpbin /DEPENDENTS $path
    foreach ($line in $lines) {
        if ($line -match '^\s+([A-Za-z0-9_.-]+\.dll)\s*$') {
            $candidate = Join-Path $sdk "bin/$($Matches[1])"
            if (Test-Path -LiteralPath $candidate) { $queue.Enqueue($candidate) }
        }
    }
}
New-Item -ItemType Directory -Force (Join-Path $runtime 'licenses') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $runtime 'etc') | Out-Null
'# Headless generated scene; no asset search paths required.' | Set-Content -LiteralPath (Join-Path $runtime 'etc/sofa.ini')
Copy-Item -LiteralPath (Join-Path $sdk 'LICENSE-LGPL.md') -Destination (Join-Path $runtime 'licenses/SOFA-LGPL.txt') -Force
Copy-Item -LiteralPath (Join-Path $sdk 'Authors.txt') -Destination (Join-Path $runtime 'licenses/SOFA-Authors.txt') -Force
Copy-Item -LiteralPath (Join-Path $sdk 'git-info.txt') -Destination (Join-Path $runtime 'licenses/SOFA-git-info.txt') -Force
Copy-Item -LiteralPath (Join-Path $sdk 'licenses/LIBTINYXML2-README.txt') -Destination (Join-Path $runtime 'licenses/TINYXML2.txt') -Force
Copy-Item -LiteralPath (Join-Path $project 'ThirdParty/physics-tools/boost_1_87_0/LICENSE_1_0.txt') -Destination (Join-Path $runtime 'licenses/BOOST.txt') -Force
Copy-Item -LiteralPath (Join-Path $project 'ThirdParty/physics-tools/eigen-3.4.0/COPYING.MPL2') -Destination (Join-Path $runtime 'licenses/EIGEN-MPL2.txt') -Force
Copy-Item -LiteralPath (Join-Path $project 'ThirdParty/physics-tools/nlohmann/LICENSE.MIT') -Destination (Join-Path $runtime 'licenses/NLOHMANN-JSON-MIT.txt') -Force
Copy-Item -LiteralPath (Join-Path $project 'ThirdParty/SOFA/TIGHT-INCLUSION-LICENSE.txt') -Destination (Join-Path $runtime 'licenses/TIGHT-INCLUSION-MIT.txt') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD-PARTY-NOTICES.txt') -Destination (Join-Path $runtime 'licenses/THIRD-PARTY-NOTICES.txt') -Force
$seen.Keys | Sort-Object | Set-Content -LiteralPath (Join-Path $runtime 'runtime-manifest.txt')
# Read the compiler identity selected by this CMake build, rather than the
# independently discovered dumpbin used to inspect DLL dependencies.
$compilerMetadata = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'build/CMakeFiles') -Filter 'CMakeCXXCompiler.cmake' -Recurse -File |
    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $compilerMetadata) { throw 'CMake compiler metadata is missing; configure and build LapPhysics before staging.' }
$compilerText = [IO.File]::ReadAllText($compilerMetadata.FullName)
$compilerVersion = [regex]::Match($compilerText, 'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)').Groups[1].Value
if (-not $compilerVersion) { throw 'Cannot read the compiler version from CMake build metadata.' }
$vcxproj = Join-Path $PSScriptRoot 'build/LapPhysics.vcxproj'
if (-not (Test-Path -LiteralPath $vcxproj)) { throw 'The generated Visual Studio project is missing.' }
$sdkVersion = [regex]::Match([IO.File]::ReadAllText($vcxproj), '<WindowsTargetPlatformVersion>([^<]+)</WindowsTargetPlatformVersion>').Groups[1].Value
if (-not $sdkVersion) { throw 'Cannot read Windows SDK version from the generated Visual Studio project.' }
$exePath = Join-Path $runtime 'LapPhysics.exe'
$exeInfo = Get-Item -LiteralPath $exePath
foreach ($compiledSource in @('main.cpp','Phase2Model.h')) {
    if ((Get-Item -LiteralPath (Join-Path $PSScriptRoot $compiledSource)).LastWriteTimeUtc -gt $exeInfo.LastWriteTimeUtc) {
        throw "Source $compiledSource is newer than LapPhysics.exe. Rebuild before writing build metadata."
    }
}
$sourceHashes = [ordered]@{}
foreach ($sourceName in @('main.cpp','Phase2Model.h','CMakeLists.txt','test_network.py')) {
    $sourceHashes[$sourceName] = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $sourceName) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json
$sofaDependency = $manifest.dependencies | Where-Object name -eq 'SOFA Windows SDK' | Select-Object -First 1
$buildInfo = [ordered]@{
    phase = 2; protocol = 2; tested_protocol = $null
    sofa_version = $sofaDependency.version; sofa_commit = $sofaDependency.source_commit
    compiler = "MSVC $compilerVersion"; windows_sdk = $sdkVersion
    cmake = $compilerMetadata.Directory.Name; build_configuration = 'Release x64'
    source_sha256 = $sourceHashes['main.cpp']; source_files_sha256 = $sourceHashes
    executable_sha256 = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    built_at_utc = $exeInfo.LastWriteTimeUtc.ToString('o'); staged_at_utc = [DateTime]::UtcNow.ToString('o')
    verification_status = 'not run by this staging operation; run RunRegression.ps1'
}
$buildInfo | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runtime 'build-info.json') -Encoding UTF8
Write-Host "Staged $($seen.Count) application and library files into $runtime"
