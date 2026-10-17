param([switch]$Install)
$ErrorActionPreference='Stop'
$ProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $Python)){
    throw 'Prepare Python 3.12 and create this project .venv first; see docs/本地开发验收.md.'
}
function Run-Python([string[]]$Arguments){
    & $Python @Arguments
    if($LASTEXITCODE -ne 0){throw "Local setup failed at $($Arguments[0]); inspect the preceding output."}
}
if($Install){
    Run-Python @('-m','pip','install','-r',(Join-Path $ProjectRoot 'requirements-high-score.txt'),'--cache-dir',(Join-Path $ProjectRoot '.cache/pip'))
}
if(-not(Test-Path -LiteralPath (Join-Path $ProjectRoot 'tools/runtime/pgsql/bin/postgres.exe')) -or
   -not(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'tools/runtime') -Filter nginx.exe -Recurse -ErrorAction SilentlyContinue)){
    Run-Python @((Join-Path $ProjectRoot 'tools/download_native_runtime.py'))
}
Run-Python @((Join-Path $ProjectRoot 'tools/prepare_native_database.py'))
& (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File (Join-Path $PSScriptRoot 'native.ps1') start
if($LASTEXITCODE -ne 0){throw 'Local business startup failed.'}
$DomainArguments=@((Join-Path $ProjectRoot 'domains/setup_local.py'),'--provision-db','--start-supervisor')
if($Install -or -not(Test-Path -LiteralPath (Join-Path $ProjectRoot '.venv-mcp-postgres/Scripts/postgres-mcp.exe'))){$DomainArguments+='--install'}
Run-Python $DomainArguments
Run-Python @((Join-Path $ProjectRoot 'tools/configure_local_coordinator.py'))
& (Join-Path $ProjectRoot 'tools/start_workbench.ps1')
if($LASTEXITCODE -ne 0){throw 'Workbench startup failed.'}
Write-Output 'Local workbench: http://127.0.0.1:8766'
