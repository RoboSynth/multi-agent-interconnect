[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='Medium')]
param([string]$ConfigPath='ops/schedule.example.json',
      [string]$OutputDirectory='runtime/startup',
      [switch]$Register,[switch]$Unregister)
$ErrorActionPreference='Stop'
if($Register -and $Unregister){throw 'Choose either -Register or -Unregister.'}
$ProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
function Project-Path([string]$Value){
    if([IO.Path]::IsPathRooted($Value)){return [IO.Path]::GetFullPath($Value)}
    return [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Value))
}
function Xml-Text([string]$Value){return [Security.SecurityElement]::Escape($Value)}
function Quote-TaskArgument([string]$Value){
    if($Value -match '["\r\n]'){throw 'Task paths must not contain quotes or newlines.'}
    return '"'+$Value+'"'
}
$Config=Project-Path $ConfigPath
$Output=Project-Path $OutputDirectory
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$Launcher=Join-Path $PSScriptRoot 'run_startup.ps1'
foreach($Path in @($Config,$Python,$Launcher,(Join-Path $PSScriptRoot 'schedule.py'))){
    if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){throw "Required startup file is missing: $Path"}
}
$Settings=Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$Address=[Uri]$Settings.workbench_url
if(-not $Address.IsAbsoluteUri -or $Address.Scheme -ne 'http' -or
   $Address.Host -notin @('127.0.0.1','localhost') -or $Address.UserInfo -or $Address.Query -or $Address.Fragment -or $Address.AbsolutePath -ne '/'){
    throw 'Startup requires a loopback HTTP workbench URL without credentials or a path.'
}
if(-not $Settings.directory){throw 'The scheduler state directory is required.'}
foreach($Name in @('inspect_interval_seconds','drill_interval_seconds')){
    if($Settings.PSObject.Properties.Name -contains $Name){
        $Value=$Settings.$Name
        if($Value -isnot [int] -and $Value -isnot [long]){throw "$Name must be integer seconds >=60."}
        if($Value -lt 60){throw "$Name must be integer seconds >=60."}
    }
}
$State=Project-Path ([string]$Settings.directory)
$UserSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$Hasher=[Security.Cryptography.SHA256]::Create()
try {$Identity=[BitConverter]::ToString($Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($ProjectRoot+'|'+$Config+'|'+$UserSid).ToLowerInvariant()))).Replace('-','').Substring(0,16)}
finally {$Hasher.Dispose()}
$TaskName='IncidentPilot-Inspect-'+$Identity
$Marker='IncidentPilot scheduled inspection '+$Identity
$Shell=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$Logs=Join-Path $Output 'logs'
$Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File '+(Quote-TaskArgument $Launcher)+
    ' -ConfigPath '+(Quote-TaskArgument $Config)+' -LogDirectory '+(Quote-TaskArgument $Logs)
$TaskXml=@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>$(Xml-Text $Marker)</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>$(Xml-Text $UserSid)</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="CurrentUser"><UserId>$(Xml-Text $UserSid)</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><Enabled>true</Enabled><Hidden>true</Hidden><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><RestartOnFailure><Interval>PT1M</Interval><Count>5</Count></RestartOnFailure></Settings>
  <Actions Context="CurrentUser"><Exec><Command>$(Xml-Text $Shell)</Command><Arguments>$(Xml-Text $Arguments)</Arguments><WorkingDirectory>$(Xml-Text $ProjectRoot)</WorkingDirectory></Exec></Actions>
</Task>
"@
[xml]$Parsed=$TaskXml
[IO.Directory]::CreateDirectory($Output) | Out-Null
$XmlPath=Join-Path $Output 'inspect-task.xml'
[IO.File]::WriteAllText($XmlPath,$TaskXml,[Text.Encoding]::Unicode)
$Action='prepared_only'
if(($Register -or $Unregister) -and $PSCmdlet.ShouldProcess($TaskName,$(if($Register){'Register login inspection task'}else{'Unregister login inspection task'}))){
    $Existing=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if($Existing -and ($Existing.Description -ne $Marker -or $Existing.Principal.UserId -ne $UserSid)){
        throw 'The existing task does not match this project, configuration and current user.'
    }
    if($Register){
        Register-ScheduledTask -TaskName $TaskName -Xml $TaskXml -Force | Out-Null
        $Action='registered_not_started'
    } elseif($Existing){
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        $Action='unregistered'
    } else {$Action='already_absent'}
}
$Summary=@{status=$Action;task_name=$TaskName;user_sid=$UserSid;task_xml=$XmlPath;
    config=$Config;project_python=$Python;scheduler_state_directory=$State;logs=$Logs;
    trigger='current_user_logon';logon_type='InteractiveToken';multiple_instances_policy='IgnoreNew';
    hidden_window=$true;fault_drills_enabled=$false;high_auto_approval=$false;
    resource_services_started=$false;task_started=$false;network_attempted=$false;
    runtime_validation='configuration_only; resource services and connected workbench must already be ready'}
[IO.File]::WriteAllText((Join-Path $Output 'startup-plan.json'),($Summary | ConvertTo-Json),[Text.Encoding]::UTF8)
$Summary | ConvertTo-Json
