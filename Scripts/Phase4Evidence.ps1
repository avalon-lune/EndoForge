$ErrorActionPreference = 'Stop'

function Get-Phase4SourceHashes([string]$Workspace) {
    $Workspace = [IO.Path]::GetFullPath($Workspace).TrimEnd('\','/')
    $UeRoot = Join-Path $Workspace 'Prototype/LapTrainer'
    $Files = @(Get-Item -LiteralPath (Join-Path $UeRoot 'LapTrainer.uproject'))
    foreach ($Name in @('Source','Config','Content')) {
        $Files += @(Get-ChildItem -LiteralPath (Join-Path $UeRoot $Name) -File -Recurse)
    }
    $Result = [ordered]@{}
    foreach ($File in ($Files | Sort-Object FullName)) {
        if (($File.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Source hashing does not traverse reparse points.' }
        $Relative = $File.FullName.Substring($Workspace.Length + 1).Replace('\','/')
        $Result[$Relative] = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $Result
}

function Assert-Phase4InputReport($Report) {
    if ($Report.phase -ne 4 -or $Report.passed -ne $true -or @($Report.failures).Count -gt 0) { throw 'Phase 4 input acceptance failed.' }
    if (-not $Report.checks -or @($Report.checks.PSObject.Properties | Where-Object Value -ne $true).Count -gt 0) { throw 'Every Phase 4 input assertion must be true.' }
    if ($null -eq $Report.metrics.safety_stop_count -or $Report.metrics.safety_stop_count -ne 0) { throw 'Input acceptance must explicitly record zero safety stops.' }
    foreach ($Metric in @('max_projection_error_px','max_render_binding_error_mm')) {
        $Value = $Report.metrics.$Metric
        if ($null -eq $Value -or [double]::IsNaN([double]$Value) -or [double]::IsInfinity([double]$Value) -or [double]$Value -lt 0) { throw "Missing or invalid metric: $Metric" }
    }
    if ([double]$Report.metrics.max_projection_error_px -gt 1.0) { throw 'Projection error exceeds one pixel.' }
    if ([double]$Report.metrics.max_render_binding_error_mm -gt 0.001) { throw 'Render-to-physical linear binding error exceeds 0.001 mm.' }
    if ($null -eq $Report.metrics.snapshots_saved -or [int]$Report.metrics.snapshots_saved -lt 1) { throw 'No frozen snapshot was saved.' }
}
