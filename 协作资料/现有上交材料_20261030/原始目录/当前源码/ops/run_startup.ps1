param([Parameter(Mandatory=$true)][string]$ConfigPath,
      [Parameter(Mandatory=$true)][string]$LogDirectory)
$ErrorActionPreference='Stop'
$ProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$Scheduler=Join-Path $PSScriptRoot 'schedule.py'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$RunId=([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))+'-'+([Guid]::NewGuid().ToString('N').Substring(0,8))
$Record=Join-Path $LogDirectory ($RunId+'.json')
$Outcome=@{run_id=$RunId;started_at_utc=[DateTime]::UtcNow.ToString('o');status='starting';config=$ConfigPath;
    fault_drills_enabled=$false;high_auto_approval=$false;resource_services_started=$false}
try {
    if(-not(Test-Path -LiteralPath $Python -PathType Leaf) -or -not(Test-Path -LiteralPath $ConfigPath -PathType Leaf)){
        throw 'Prepare the project Python environment and scheduler configuration first.'
    }
    # Only this new task process is filtered; the user's environment is untouched.
    $AllowedNames=@('SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','APPDATA','LOCALAPPDATA',
        'USERPROFILE','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','SYSTEMDRIVE','HOMEDRIVE','HOMEPATH',
        'USERNAME','COMPUTERNAME','OS','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE')
    foreach($Entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()){
        if($Entry.Key -notin $AllowedNames){[Environment]::SetEnvironmentVariable($Entry.Key,$null,'Process')}
    }
    $env:PYTHONUTF8='1'
    $env:PYTHONUNBUFFERED='1'
    function Quote-TaskArgument([string]$Value){
        if($Value -match '["\r\n]'){throw 'Task paths must not contain quotes or newlines.'}
        return '"'+$Value+'"'
    }
    $Arguments=@('-B','-u',(Quote-TaskArgument $Scheduler),'--config',(Quote-TaskArgument $ConfigPath))
    $Process=Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -PassThru -RedirectStandardOutput (Join-Path $LogDirectory ($RunId+'.stdout.log')) `
        -RedirectStandardError (Join-Path $LogDirectory ($RunId+'.stderr.log'))
    $Outcome.status='running'
    $Outcome.scheduler_pid=$Process.Id
    $Outcome | ConvertTo-Json | Set-Content -LiteralPath $Record -Encoding UTF8
    $Process.WaitForExit()
    $Process.Refresh()
    $Outcome.status='finished'
    $Outcome.actual_os_exit_code=$Process.ExitCode
    $Outcome.finished_at_utc=[DateTime]::UtcNow.ToString('o')
    $Outcome | ConvertTo-Json | Set-Content -LiteralPath $Record -Encoding UTF8
    exit $Process.ExitCode
} catch {
    $Outcome.status='launcher_failed'
    $Outcome.error=$_.Exception.Message
    $Outcome.finished_at_utc=[DateTime]::UtcNow.ToString('o')
    $Outcome | ConvertTo-Json | Set-Content -LiteralPath $Record -Encoding UTF8
    throw
}
