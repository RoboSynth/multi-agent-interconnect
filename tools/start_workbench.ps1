param([int]$Port=8766,[string]$ConfigPath='',[string]$OutputDirectory='',
      [switch]$CheckEnvironmentOnly,[string]$EnvironmentCheckOutput='')
$ErrorActionPreference='Stop'
$ProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$Config=if($ConfigPath){if([IO.Path]::IsPathRooted($ConfigPath)){$ConfigPath}else{Join-Path $ProjectRoot $ConfigPath}}else{Join-Path $ProjectRoot 'runtime/local-coordinator.json'}
$OutputDir=if($OutputDirectory){if([IO.Path]::IsPathRooted($OutputDirectory)){$OutputDirectory}else{Join-Path $ProjectRoot $OutputDirectory}}else{Join-Path $ProjectRoot 'artifacts/high-score-workbench'}
if(-not(Test-Path -LiteralPath $Python)){throw 'Prepare the project Python environment first.'}
function Start-IsolatedWorkbenchProcess([string[]]$Arguments,[string]$Stdout,[string]$Stderr) {
    $AllowedNames=@('SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','APPDATA','LOCALAPPDATA',
        'USERPROFILE','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','SYSTEMDRIVE','HOMEDRIVE','HOMEPATH',
        'USERNAME','OS','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','PYTHONUTF8','PYTHONIOENCODING',
        'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','INCIDENT_LLM_BASE_URL','INCIDENT_LLM_MODEL','INCIDENT_LLM_API_KEY')
    $LaunchEnvironment=@{}
    foreach($Entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
        $LaunchEnvironment[$Entry.Key]=if($Entry.Key -in $AllowedNames){$Entry.Value}else{$null}
    }
    return (Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -UseNewEnvironment -Environment $LaunchEnvironment -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr)
}
if($CheckEnvironmentOnly) {
    if(-not $EnvironmentCheckOutput){$EnvironmentCheckOutput=Join-Path $OutputDir 'launcher-env-check.json'}
    $EnvironmentCheckOutput=[IO.Path]::GetFullPath($EnvironmentCheckOutput)
    New-Item -ItemType Directory -Path (Split-Path -Parent $EnvironmentCheckOutput) -Force | Out-Null
    $ProbeCode="import os,json,sys; blocked=[k for k in os.environ if k.upper().startswith('PG') or k.upper() in {'DATABASE_URI','DATABASE_URL','APP_ADMIN_TOKEN','POSTGRES_PASSWORD','ORDERS_DB_PASSWORD','OPS_SUPERVISOR_TOKEN','DOCKER_HOST','DOCKER_CERT_PATH','DOCKER_TLS_VERIFY'}]; print(json.dumps({'probe_only':True,'launch_boundary':'same isolated process function as workbench','resource_credential_variable_names':sorted(blocked),'passed':not blocked})); sys.exit(bool(blocked))"
    $Probe=Start-IsolatedWorkbenchProcess @('-c',('"'+$ProbeCode+'"')) $EnvironmentCheckOutput ($EnvironmentCheckOutput+'.stderr.log')
    $Probe.WaitForExit()
    $Probe.Refresh()
    if($Probe.ExitCode -ne 0){throw 'Coordinator launch environment isolation failed; inspect the credential-name-only probe result.'}
    Get-Content -LiteralPath $EnvironmentCheckOutput -Raw | Write-Output
    exit 0
}
if(-not(Test-Path -LiteralPath $Config)){throw 'Run tools/configure_local_coordinator.py after preparing the local domains.'}
$Existing=$null
try { $Existing=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2 } catch { }
if($Existing){
    $ExpectedMode=(Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json).mode
    if($Existing.mode -ne $ExpectedMode){throw 'Selected port is occupied by another service.'}
    Write-Output "Workbench is already running at http://127.0.0.1:$Port"
    exit 0
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$Arguments=@('"'+(Join-Path $ProjectRoot 'workbench_server.py')+'"','--port',[string]$Port,'--config','"'+$Config+'"','--output','"'+$OutputDir+'"')
$Started=Start-IsolatedWorkbenchProcess $Arguments (Join-Path $OutputDir 'server.stdout.log') (Join-Path $OutputDir 'server.stderr.log')
$MetadataName=if($Port -eq 8766){'runtime/workbench-server.json'}else{"runtime/workbench-server-$Port.json"}
@{launcher_pid=$Started.Id;port=$Port;config=$Config;launch_environment='system-and-model-allowlist'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ProjectRoot $MetadataName) -Encoding utf8
Write-Output "Workbench starting at http://127.0.0.1:$Port; log: $OutputDir"
