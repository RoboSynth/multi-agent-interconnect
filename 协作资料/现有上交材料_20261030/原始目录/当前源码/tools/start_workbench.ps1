param([int]$Port=8766,[string]$ConfigPath='',[string]$OutputDirectory='',
      [switch]$CheckEnvironmentOnly,[string]$EnvironmentCheckOutput='',
      [ValidateRange(1,300)][int]$StartupTimeoutSeconds=45)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion -lt [Version]'7.4'){throw 'Use PowerShell 7.4 or later to start the local workbench.'}
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
$Config=[IO.Path]::GetFullPath($Config)
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
$ExpectedConfig=Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$ExpectedMode=$ExpectedConfig.mode
$ExpectedConfigSha=(Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash.ToLowerInvariant()
function Assert-WorkbenchConfiguration($State) {
    if($State.mode -ne $ExpectedMode -or $State.config_sha256 -ne $ExpectedConfigSha){
        throw 'The running workbench has a different or unverified configuration. Explicitly restart it with the selected config; no process was stopped.'
    }
}
function Get-WorkbenchRuntimePid($State,$Launcher) {
    $RuntimePid=0
    if(-not [int]::TryParse([string]$State.pid,[ref]$RuntimePid) -or $RuntimePid -le 0){throw 'Workbench returned an invalid runtime PID.'}
    if($RuntimePid -eq $Launcher.Id){return $RuntimePid}
    $Process=Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $RuntimePid" -ErrorAction Stop
    if(-not $Process -or $Process.ParentProcessId -ne $Launcher.Id){throw "Port $Port is responding from another process; the runtime is not the launched process or its direct Python child."}
    $PythonPaths=@($Python)
    $VenvConfig=Join-Path $ProjectRoot '.venv/pyvenv.cfg'
    if(Test-Path -LiteralPath $VenvConfig){
        foreach($Line in Get-Content -LiteralPath $VenvConfig){
            if($Line -match '^executable\s*=\s*(.+)$'){$PythonPaths += $Matches[1].Trim()}
            elseif($Line -match '^home\s*=\s*(.+)$'){$PythonPaths += Join-Path $Matches[1].Trim() 'python.exe'}
        }
    }
    $PythonPaths=@($PythonPaths | ForEach-Object {[IO.Path]::GetFullPath($_)})
    if(-not $Process.ExecutablePath -or [IO.Path]::GetFullPath($Process.ExecutablePath) -notin $PythonPaths){throw 'Workbench direct child has an unexpected Python executable.'}
    if(-not ('IncidentWorkbenchCommandLine' -as [type])){
        Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class IncidentWorkbenchCommandLine {
    [DllImport("shell32.dll", SetLastError=true)]
    static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string command, out int count);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
    public static string[] Parse(string command) {
        int count; IntPtr memory=CommandLineToArgvW(command,out count);
        if(memory==IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
        try { var args=new string[count]; for(int i=0;i<count;i++) args[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory,i*IntPtr.Size)); return args; }
        finally { LocalFree(memory); }
    }
}
'@
    }
    if(-not $Process.CommandLine){throw 'Workbench direct child command line could not be verified.'}
    $Command=[IncidentWorkbenchCommandLine]::Parse($Process.CommandLine)
    if($Command.Count -ne 8 -or [IO.Path]::GetFullPath($Command[0]) -notin $PythonPaths -or
       [IO.Path]::GetFullPath($Command[1]) -ne (Join-Path $ProjectRoot 'workbench_server.py') -or
       $Command[2] -ne '--port' -or $Command[3] -ne [string]$Port -or
       $Command[4] -ne '--config' -or [IO.Path]::GetFullPath($Command[5]) -ne $Config -or
       $Command[6] -ne '--output' -or [IO.Path]::GetFullPath($Command[7]) -ne $OutputDir){throw 'Workbench direct child command line does not match this script, config, output and port.'}
    return $RuntimePid
}
$Existing=$null
try { $Existing=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2 -NoProxy } catch { }
if($Existing){
    Assert-WorkbenchConfiguration $Existing
    if($Existing.connected -ne $true -or $Existing.connection_error){throw 'The existing workbench has no healthy participant connection. Resolve the connection error and explicitly restart it; inspect its logs.'}
    Write-Output "Workbench is already running at http://127.0.0.1:$Port"
    exit 0
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$Arguments=@('"'+(Join-Path $ProjectRoot 'workbench_server.py')+'"','--port',[string]$Port,'--config','"'+$Config+'"','--output','"'+$OutputDir+'"')
$LaunchId=(Get-Date -Format 'yyyyMMddTHHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$Stdout=Join-Path $OutputDir ("server-$LaunchId.stdout.log")
$Stderr=Join-Path $OutputDir ("server-$LaunchId.stderr.log")
$Started=Start-IsolatedWorkbenchProcess $Arguments $Stdout $Stderr
$Timer=[Diagnostics.Stopwatch]::StartNew()
$Ready=$false
while($Timer.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds){
    $Started.Refresh()
    if($Started.HasExited){
        $Started.WaitForExit()
        throw "Workbench process $($Started.Id) exited with code $($Started.ExitCode) before becoming ready. Inspect $Stderr"
    }
    $State=$null
    try { $State=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2 -NoProxy } catch { }
    if($State){
        $RuntimePid=Get-WorkbenchRuntimePid $State $Started
        Assert-WorkbenchConfiguration $State
        if($State.connection_error){throw "Workbench participant connection failed. Inspect $Stderr"}
        if($State.connected -eq $true){$Ready=$true;break}
    }
    Start-Sleep -Milliseconds 250
}
if(-not $Ready){throw "Workbench process $($Started.Id) did not become connected within $StartupTimeoutSeconds seconds. Inspect $Stderr"}
$MetadataName=if($Port -eq 8766){'runtime/workbench-server.json'}else{"runtime/workbench-server-$Port.json"}
@{launcher_pid=$Started.Id;runtime_pid=$RuntimePid;port=$Port;config=$Config;config_sha256=$ExpectedConfigSha;launch_environment='system-and-model-allowlist';stdout=$Stdout;stderr=$Stderr} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ProjectRoot $MetadataName) -Encoding utf8
Write-Output "Workbench ready at http://127.0.0.1:$Port; log: $OutputDir"
exit 0
