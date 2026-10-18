param([switch]$Install,[switch]$EnableLocalModel)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion -lt [Version]'7.4'){throw 'Use PowerShell 7.4 or later for local startup.'}
$ProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $Python)){
    throw 'Prepare Python 3.12 and create this project .venv first; see docs/本地开发验收.md.'
}
function Run-Python([string[]]$Arguments){
    & $Python @Arguments
    if($LASTEXITCODE -ne 0){throw "Local setup failed at $($Arguments[0]); inspect the preceding output."}
}
$CoordinatorArguments=@((Join-Path $ProjectRoot 'tools/configure_local_coordinator.py'),'--config',(Join-Path $ProjectRoot 'runtime/local-coordinator.json'))
if($EnableLocalModel){
    $CoordinatorArguments+=@('--enable-llm','--model-base-url','http://127.0.0.1:8089/v1','--model','Qwen3-1.7B-Q8_0')
}
# Validate existing or proposed config before installing or touching resources.
Run-Python ($CoordinatorArguments+@('--check'))
if($Install){
    Run-Python @('-m','pip','install','-r',(Join-Path $ProjectRoot 'requirements-high-score.txt'),'--cache-dir',(Join-Path $ProjectRoot '.cache/pip'))
}
$NginxExecutable=Join-Path $ProjectRoot 'tools/runtime/nginx-1.30.6/nginx.exe'
$RuntimeFile=Join-Path $PSScriptRoot 'native-runtime.json'
if(Test-Path -LiteralPath $RuntimeFile){
    $Runtime=Get-Content -LiteralPath $RuntimeFile -Raw | ConvertFrom-Json -AsHashtable
    if($Runtime.nginx_bin){
        $NginxExecutable=$Runtime.nginx_bin
        if(-not(Test-Path -LiteralPath $NginxExecutable -PathType Leaf)){
            throw 'Configured nginx executable is missing; restore it or correct deploy/native-runtime.json before starting.'
        }
    }
}
if(-not(Test-Path -LiteralPath (Join-Path $ProjectRoot 'tools/runtime/pgsql/bin/postgres.exe')) -or
   -not(Test-Path -LiteralPath $NginxExecutable -PathType Leaf)){
    Run-Python @((Join-Path $ProjectRoot 'tools/download_native_runtime.py'))
}
Run-Python @((Join-Path $ProjectRoot 'tools/prepare_native_database.py'))
& (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File (Join-Path $PSScriptRoot 'native.ps1') start
if($LASTEXITCODE -ne 0){throw 'Local business startup failed.'}
$DomainArguments=@((Join-Path $ProjectRoot 'domains/setup_local.py'),'--provision-db','--start-supervisor')
if($Install -or -not(Test-Path -LiteralPath (Join-Path $ProjectRoot '.venv-mcp-postgres/Scripts/postgres-mcp.exe'))){$DomainArguments+='--install'}
Run-Python $DomainArguments
Run-Python $CoordinatorArguments
& (Join-Path $ProjectRoot 'tools/start_workbench.ps1')
if($LASTEXITCODE -ne 0){throw 'Workbench startup failed.'}
Write-Output 'Local workbench: http://127.0.0.1:8766'
