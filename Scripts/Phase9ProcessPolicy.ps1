# Process-scoped timing for a newly launched EndoForge endpoint on Windows.
# Windows 11 may ignore timeBeginPeriod requests for an invisible window.
# This honors the endpoint's existing requests; it does not request a global
# timer period, change priority/EcoQoS, or modify any other application.
# https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation
if (-not ('EndoForgePhase9.ProcessTiming' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace EndoForgePhase9 {
    [StructLayout(LayoutKind.Sequential)]
    public struct PowerPolicy { public UInt32 Version, ControlMask, StateMask; }
    public static class ProcessTiming {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool QueryFullProcessImageName(IntPtr process, UInt32 flags,
            System.Text.StringBuilder filename, ref UInt32 size);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetProcessInformation(IntPtr process, int infoClass,
            ref PowerPolicy state, UInt32 size);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetProcessInformation(IntPtr process, int infoClass,
            ref PowerPolicy state, UInt32 size);
    }
}
'@
}

function Set-EndoForgeOwnedTimerPolicy {
    param(
        [Parameter(Mandatory=$true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory=$true)][string]$ExpectedExecutable,
        [Parameter(Mandatory=$true)][DateTime]$CreatedAfterUtc,
        [Parameter(Mandatory=$true)][string]$Receipt
    )
    $Process.Refresh()
    $Handle = $Process.Handle # Keep the actual process object alive, never reopen a PID.
    # Read the image identity from the retained kernel handle. MainModule can
    # temporarily be empty while a newly started UE image initializes.
    $ImagePath = [Text.StringBuilder]::new(32768)
    $ImageLength = [uint32]$ImagePath.Capacity
    if (-not [EndoForgePhase9.ProcessTiming]::QueryFullProcessImageName($Handle,0,$ImagePath,[ref]$ImageLength)) {
        throw ('Cannot verify owned process image (Win32 '+[Runtime.InteropServices.Marshal]::GetLastWin32Error()+').')
    }
    $ActualPath = [IO.Path]::GetFullPath($ImagePath.ToString())
    $ExpectedPath = [IO.Path]::GetFullPath($ExpectedExecutable)
    $Created = $Process.StartTime.ToUniversalTime()
    if ($Process.HasExited -or -not [String]::Equals($ActualPath,$ExpectedPath,[StringComparison]::OrdinalIgnoreCase) -or $Created -lt $CreatedAfterUtc.ToUniversalTime()) {
        throw 'Timer policy refused: endpoint is not the expected newly launched process.'
    }
    $Before = New-Object EndoForgePhase9.PowerPolicy
    $Before.Version = 1
    $QueryOk = [EndoForgePhase9.ProcessTiming]::GetProcessInformation($Handle,4,[ref]$Before,12)
    $ErrorCode = if ($QueryOk) { 0 } else { [Runtime.InteropServices.Marshal]::GetLastWin32Error() }
    $Applied = $false
    $After = New-Object EndoForgePhase9.PowerPolicy
    $After.Version = 1
    if ($QueryOk) {
        $Requested = New-Object EndoForgePhase9.PowerPolicy
        $Requested.Version = 1
        $Requested.ControlMask = $Before.ControlMask -bor 4
        $Requested.StateMask = $Before.StateMask -band ([uint32]4294967291)
        $SetOk = [EndoForgePhase9.ProcessTiming]::SetProcessInformation($Handle,4,[ref]$Requested,12)
        if (-not $SetOk) { $ErrorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error() }
        else {
            $Readback = [EndoForgePhase9.ProcessTiming]::GetProcessInformation($Handle,4,[ref]$After,12)
            if (-not $Readback) { $ErrorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error() }
            else { $Applied = $After.ControlMask -eq $Requested.ControlMask -and $After.StateMask -eq $Requested.StateMask }
        }
    }
    $Record = [ordered]@{
        schema='endoforge.phase9.owned-process-timer-policy.v1';pid=$Process.Id
        executable=$ActualPath;created_utc=$Created.ToString('o');verified_new_owned_process=$true
        before=[ordered]@{control_mask=$Before.ControlMask;state_mask=$Before.StateMask}
        after=[ordered]@{control_mask=$After.ControlMask;state_mask=$After.StateMask}
        applied=$Applied;win32_error=$ErrorCode
        scope='Only this newly launched endpoint honors its existing timer requests. Other power-policy bits are preserved. No global timer, priority or user-application changes. The policy ends with this process.'
    }
    $ReceiptPath = [IO.Path]::GetFullPath($Receipt)
    $Stream = [IO.File]::Open($ReceiptPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try {
        $Bytes = [Text.Encoding]::UTF8.GetBytes(($Record | ConvertTo-Json -Depth 5))
        $Stream.Write($Bytes,0,$Bytes.Length)
    } finally { $Stream.Dispose() }
    if (-not $Applied) { Write-Warning "Endpoint timer policy unavailable (Win32 $ErrorCode); measured runtime performance still determines acceptance." }
    return [pscustomobject]$Record
}
