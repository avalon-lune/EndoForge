param([string]$RunName = ('phase4-launcher-process-' + (Get-Date -Format 'yyyyMMdd-HHmmss')), [int]$Port = 47329)
$ErrorActionPreference = 'Stop'
$Workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Root = [IO.Path]::GetFullPath((Join-Path $Workspace 'output/verification'))
$Directory = [IO.Path]::GetFullPath((Join-Path $Root $RunName))
if (-not $Directory.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid test output directory.' }
if (Test-Path -LiteralPath $Directory) { throw 'Use a fresh test output directory.' }
New-Item -ItemType Directory -Path $Directory | Out-Null
$Exe = Join-Path $Workspace 'Physics/runtime/LapPhysics.exe'
$Hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
if (@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object Port -eq $Port).Count) { throw 'Probe port is occupied; existing processes were not stopped.' }
$Process = $null
$Client = $null
try {
    $Process = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path -Parent $Exe) -ArgumentList @('--port',"$Port",'--exit-after-client','--session-dir',('"' + $Directory + '/native-sessions"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Directory 'physics.stdout.log') -RedirectStandardError (Join-Path $Directory 'physics.stderr.log')
    $CachedHandle = $Process.Handle
    $Ready = $false
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $Deadline) {
        $Process.Refresh()
        if ($Process.HasExited) { throw 'Native process exited before accepting the probe.' }
        $Owner = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Where-Object OwningProcess -eq $Process.Id)
        if ($Owner.Count) { $Ready = $true; break }
        Start-Sleep -Milliseconds 50
    }
    if (-not $Ready) { throw 'Native process did not listen within 30 seconds.' }
    $Client = New-Object Net.Sockets.TcpClient
    $Client.ReceiveTimeout = 10000
    $Client.Connect('127.0.0.1', $Port)
    $Reader = New-Object IO.StreamReader($Client.GetStream())
    $Hello = $Reader.ReadLine() | ConvertFrom-Json
    if ($Hello.type -ne 'hello' -or $Hello.protocol -ne 4) { throw 'No Phase 4 handshake.' }
    $Reader.Dispose()
    $Client.Dispose()
    $Client = $null
    # Exercise the exact already-exited/Refresh path that previously lost ExitCode.
    $Deadline = [DateTime]::UtcNow.AddSeconds(10)
    do { $Process.Refresh(); if ($Process.HasExited) { break }; Start-Sleep -Milliseconds 50 } while ([DateTime]::UtcNow -lt $Deadline)
    $Exited = $Process.WaitForExit(10000)
    if ($Exited) { $Process.WaitForExit() }
    $Code = if ($Exited) { $Process.ExitCode } else { $null }
    if (-not $Exited -or $null -eq $Code -or $Code -ne 0) { throw "Exit code was not a verified zero: $Code" }
    if ((Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) { throw 'Executable changed during probe.' }
    [ordered]@{phase=4;passed=$true;kind='owned native process handle and graceful-exit regression';powershell=$PSVersionTable.PSVersion.ToString();native_exit_code=$Code;cached_handle=[int64]$CachedHandle;executable_sha256=$Hash;tested_at_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Directory 'launcher-process-result.json') -Encoding UTF8
    Write-Host "Native handle/exit regression passed on PowerShell $($PSVersionTable.PSVersion): $Directory"
}
finally {
    if ($Client) { $Client.Dispose() }
    if ($Process) { if (-not $Process.HasExited) { $Process.Kill(); $Process.WaitForExit(5000) | Out-Null }; $Process.Dispose() }
}
