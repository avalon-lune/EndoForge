$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$cmake = Join-Path $project 'ThirdParty/physics-tools/cmake-4.4.4-windows-x86_64/bin/cmake.exe'
& $cmake -S $PSScriptRoot -B (Join-Path $PSScriptRoot 'build') -G 'Visual Studio 17 2022' -A x64
if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed' }
& $cmake --build (Join-Path $PSScriptRoot 'build') --config Release --parallel 4
if ($LASTEXITCODE -ne 0) { throw 'C++ build failed' }
& (Join-Path $PSScriptRoot 'stage-runtime.ps1')
