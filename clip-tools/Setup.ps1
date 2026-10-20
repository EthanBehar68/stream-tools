# Adds clip-tools to the user PATH so `cutclip` and `stitch` work from any folder,
# and offers to install Python and ffmpeg with winget. No admin needed.
#   powershell -ExecutionPolicy Bypass -File .\Setup.ps1              install
#   powershell -ExecutionPolicy Bypass -File .\Setup.ps1 -Uninstall   remove from PATH
# Re-run it if the drive letter changes.
param(
    [switch]$Uninstall,
    [switch]$SkipDependencies
)
$ErrorActionPreference = 'Stop'

$ToolDir = (Resolve-Path $PSScriptRoot).Path.TrimEnd('\')

# Read PATH raw from the registry so entries like %USERPROFILE%\... stay unexpanded.
$EnvKey = 'HKCU:\Environment'
$Raw = (Get-Item $EnvKey).GetValue('Path', '', 'DoNotExpandEnvironmentNames')
$Entries = @($Raw -split ';' | Where-Object { $_ -ne '' })

# Drop this folder and stale copies (another drive letter, or the old clip-stitch name).
$Kept = @($Entries | Where-Object {
    $e = $_.TrimEnd('\')
    -not ($e -ieq $ToolDir -or $e -match '\\clip-tools$' -or $e -match '\\clip-stitch$')
})
$Removed = $Entries.Count - $Kept.Count

if ($Uninstall) {
    $NewEntries = $Kept
} else {
    $NewEntries = $Kept + $ToolDir
}
$New = $NewEntries -join ';'
if ($Raw.EndsWith(';') -and $New) { $New += ';' }  # keep the original's trailing ;

if ($New -ne $Raw) {
    Set-ItemProperty -Path $EnvKey -Name Path -Value $New -Type ExpandString
    # Tell Explorer PATH changed, so new terminals pick it up without signing out.
    Add-Type -Namespace Win32 -Name Env -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam,
    string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@
    $Result = [UIntPtr]::Zero
    [void][Win32.Env]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$Result)
}

if ($Uninstall) {
    Write-Host "Removed clip-tools from your PATH ($Removed entr$(if ($Removed -eq 1) {'y'} else {'ies'}))."
    return
}

$env:Path = (($env:Path -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ine $ToolDir }) + $ToolDir) -join ';'
Write-Host "Added $ToolDir to your PATH."
if ($Removed -gt 0 -and -not ($Entries | Where-Object { $_.TrimEnd('\') -ieq $ToolDir })) {
    Write-Host "Removed $Removed old clip-tools PATH entr$(if ($Removed -eq 1) {'y'} else {'ies'})."
}

function Test-Python {
    foreach ($cmd in 'py', 'python') {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            # The Microsoft Store "python" alias exists but fails; run it to be sure.
            try {
                & $cmd -c 'import sys' 2>$null
                if ($LASTEXITCODE -eq 0) { return $true }
            } catch { }
        }
    }
    return $false
}

$Missing = @()
if (-not (Test-Python)) { $Missing += @{ Name = 'Python'; Id = 'Python.Python.3.12' } }
if (-not ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue))) {
    $Missing += @{ Name = 'ffmpeg'; Id = 'Gyan.FFmpeg' }
}

if ($Missing.Count -gt 0) {
    Write-Host ''
    Write-Host "Missing: $(($Missing | ForEach-Object { $_.Name }) -join ', ')"
    $HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
    if ($SkipDependencies -or -not $HasWinget) {
        foreach ($m in $Missing) { Write-Host "  Install: winget install -e --id $($m.Id)" }
    } else {
        foreach ($m in $Missing) {
            $Answer = Read-Host "Install $($m.Name) with winget now? [Y/n]"
            if ($Answer -eq '' -or $Answer -match '^[Yy]') {
                winget install -e --id $m.Id --accept-source-agreements --accept-package-agreements
            } else {
                Write-Host "  Skipped. Later: winget install -e --id $($m.Id)"
            }
        }
    }
}

Write-Host ''
Write-Host 'Done. Open a new terminal, then run:  stitch --check'
