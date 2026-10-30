param([ValidateRange(1,3600)][int]$TimeoutSeconds=120)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion -lt [Version]'7.4'){throw 'Use PowerShell 7.4 or later for local shutdown.'}
$ProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $Python -PathType Leaf)){
    throw 'Restore this project .venv before shutdown; do not stop processes by name.'
}
& $Python (Join-Path $ProjectRoot 'tools/local_shutdown.py') --timeout-seconds $TimeoutSeconds --pwsh (Join-Path $PSHOME 'pwsh.exe')
if($LASTEXITCODE -ne 0){throw 'Local shutdown did not complete; inspect runtime/local-down reports and retained registrations.'}
