# Run debug/run_tests.py against every Blender sandbox.
# English-only text on purpose: Windows PowerShell 5.1 mis-decodes UTF-8 without BOM.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File run_matrix.ps1
#   powershell -ExecutionPolicy Bypass -File run_matrix.ps1 -Versions "5.1.0","5.3"
#   powershell -ExecutionPolicy Bypass -File run_matrix.ps1 -SandboxRoot "R:\sandbox_blender"

param(
    [string]$SandboxRoot = "R:\sandbox_blender",
    [string[]]$Versions = @(),
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"
$debugDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$addonDir = (Split-Path -Parent $debugDir).TrimEnd('\')
$addonName = Split-Path -Leaf $addonDir

function Find-BlenderExe {
    param([string]$Dir)
    $direct = Join-Path $Dir "blender.exe"
    if (Test-Path $direct) { return $direct }
    $nested = Get-ChildItem -Path $Dir -Filter "blender.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($nested) { return $nested.FullName }
    return $null
}

$sandboxes = Get-ChildItem -Path $SandboxRoot -Directory -Filter "blender-*" | Sort-Object Name
$rows = @()

foreach ($box in $sandboxes) {
    $exe = Find-BlenderExe -Dir $box.FullName
    if (-not $exe) { continue }

    $versionTag = $box.Name -replace "^blender-", ""

    # Skip sandboxes older than the add-on minimum (4.5): Blender refuses to enable it there.
    if ($versionTag -match "^(\d+)\.(\d+)") {
        $major = [int]$Matches[1]; $minor = [int]$Matches[2]
        if ($major -lt 4 -or ($major -eq 4 -and $minor -lt 5)) { continue }
    }
    if ($Versions.Count -gt 0) {
        $matched = $false
        foreach ($wanted in $Versions) {
            if ($versionTag -like "$wanted*") { $matched = $true; break }
        }
        if (-not $matched) { continue }
    }

    $root = Split-Path -Parent $exe
    $addonsDir = Join-Path $root "portable\scripts\addons"
    if (-not (Test-Path $addonsDir)) { continue }
    $target = Join-Path $addonsDir $addonName

    # Never copy the add-on onto itself: this script usually lives inside it.
    if ($target.TrimEnd('\') -ieq $addonDir) {
        Write-Host ("skip {0}: target is the source add-on" -f $versionTag)
    }
    else {
        # Replace the sandbox copy (sandboxes are disposable).
        # Do not rename to "__backup": Blender would scan it as a second add-on.
        if (Test-Path $target) { Remove-Item $target -Recurse -Force }
        robocopy $addonDir $target /E /XD "__pycache__" ".git" /XF "*.zip" /NFL /NDL /NJH /NJS /NP | Out-Null
    }

    $stdout = Join-Path $env:TEMP "bet_matrix_$versionTag.out.log"
    $stderr = Join-Path $env:TEMP "bet_matrix_$versionTag.err.log"
    $proc = Start-Process -FilePath $exe `
        -ArgumentList "--python", (Join-Path $target "debug\run_tests.py") `
        -WindowStyle Minimized `
        -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        Stop-Process -Id $proc.Id -Force
        $rows += [pscustomobject]@{ Version = $versionTag; Pass = "-"; Fail = "TIMEOUT" }
        continue
    }

    $resultLine = Get-Content $stdout -Encoding UTF8 | Select-String -Pattern "^BET_RESULT " | Select-Object -Last 1
    if ($resultLine) {
        $json = $resultLine.Line.Substring("BET_RESULT ".Length) | ConvertFrom-Json
        $rows += [pscustomobject]@{
            Version = $versionTag
            Pass    = $json.pass
            Fail    = $json.fail
            Seconds = $json.seconds
        }
        foreach ($failed in $json.cases) {
            Write-Host ("  FAIL [{0}] {1} :: {2}" -f $versionTag, $failed.name, $failed.detail)
        }
    }
    else {
        $rows += [pscustomobject]@{ Version = $versionTag; Pass = "-"; Fail = "NO RESULT" }
        Write-Host ("  no BET_RESULT for {0}, see {1}" -f $versionTag, $stdout)
    }
}

Write-Host ""
$rows | Format-Table -AutoSize
$totalFail = ($rows | Measure-Object -Property Fail -Sum).Sum
if ($totalFail -gt 0) { exit 1 }
exit 0
