<#
.SYNOPSIS
    Agent Continuity Steward (SCS_AG_v2) — Windows PowerShell Wrapper (scs.ps1)
.DESCRIPTION
    Zero external dependencies. Discovers active Python virtual environment
    or system Python and executes SCS CLI commands.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

# 1. Check if VIRTUAL_ENV is active in current session
if ($env:VIRTUAL_ENV) {
    $venvCli = Join-Path $env:VIRTUAL_ENV "Scripts\scs.exe"
    if (Test-Path $venvCli) {
        & $venvCli @ScriptArgs
        exit $LASTEXITCODE
    }
    $venvPy = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
    if (Test-Path $venvPy) {
        & $venvPy -m engine.scs_cli @ScriptArgs
        exit $LASTEXITCODE
    }
}

# 2. Check local workspace .venv in current directory
$localCli = Join-Path (Get-Location) ".venv\Scripts\scs.exe"
if (Test-Path $localCli) {
    & $localCli @ScriptArgs
    exit $LASTEXITCODE
}
$localPy = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (Test-Path $localPy) {
    & $localPy -m engine.scs_cli @ScriptArgs
    exit $LASTEXITCODE
}

# 3. Check repo root .venv
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoCli = Join-Path $repoRoot ".venv\Scripts\scs.exe"
if (Test-Path $repoCli) {
    & $repoCli @ScriptArgs
    exit $LASTEXITCODE
}
$repoPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $repoPy) {
    $env:PYTHONPATH = "$repoRoot\src;$env:PYTHONPATH"
    & $repoPy -m engine.scs_cli @ScriptArgs
    exit $LASTEXITCODE
}

# 4. Fallback to system Python
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) {
    $env:PYTHONPATH = "$repoRoot\src;$env:PYTHONPATH"
    & python -m engine.scs_cli @ScriptArgs
    exit $LASTEXITCODE
}

Write-Error "[X] Error: Python was not found in your environment or active virtualenv. Please activate a virtual environment or install Python 3.10+."
exit 1
