param(
    [Parameter(Mandatory=$true)][string]$AcsFile,
    [Parameter(Mandatory=$true)][string]$ObservationFile,
    [long]$WindowHandle=5445952
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$acs=Get-Content -LiteralPath $AcsFile -Raw -Encoding utf8 | ConvertFrom-Json
if ($acs.aic) { throw 'New registration must not claim an existing AIC' }
if (Test-Path -LiteralPath $ObservationFile) { throw 'An observation already exists; inspect the existing registration before repeating' }
function Window { [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle) }
function Control([string]$name,$type) {
    $c=[System.Windows.Automation.AndCondition]::new(
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$name),
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type))
    (Window).FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)
}
function Invoke-Control([string]$name,$type) {
    $n=Control $name $type
    if ($null -eq $n -or -not $n.Current.IsEnabled) { throw "Enabled control missing: $name" }
    $n.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
function Wait-Control([string]$name,$type) {
    $deadline=[DateTime]::UtcNow.AddSeconds(8)
    do {
        $n=Control $name $type
        if ($null -ne $n) { return $n }
        Start-Sleep -Milliseconds 150
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Control not found after navigation: $name"
}
Invoke-Control '我的智能体' ([System.Windows.Automation.ControlType]::Hyperlink)
$null=Wait-Control '注册' ([System.Windows.Automation.ControlType]::Button)
if ($null -ne (Control $acs.name ([System.Windows.Automation.ControlType]::DataItem))) {
    throw 'This agent name already exists. Inspect it instead of registering again.'
}
Invoke-Control '注册' ([System.Windows.Automation.ControlType]::Button)
$null=Wait-Control 'ACS' ([System.Windows.Automation.ControlType]::Edit)
& "$PSScriptRoot\edge-register-form.ps1" -AcsFile $AcsFile -WindowHandle $WindowHandle -Save | Out-Null
$null=Wait-Control $acs.name ([System.Windows.Automation.ControlType]::DataItem)
& "$PSScriptRoot\edge-agent-row.ps1" -AgentName $acs.name -Action '提交审核' -WindowHandle $WindowHandle | Out-Null
$null=Wait-Control '确定要提交此智能体进行审核吗？' ([System.Windows.Automation.ControlType]::Text)
Invoke-Control '是' ([System.Windows.Automation.ControlType]::Button)
# Observe the created row, never submit a second time to resolve delayed UI.
Start-Sleep -Milliseconds 250
& "$PSScriptRoot\edge-agent-row.ps1" -AgentName $acs.name -Action '详情' -WindowHandle $WindowHandle | Out-Null
$null=Wait-Control '* 名称' ([System.Windows.Automation.ControlType]::Edit)
$deadline=[DateTime]::UtcNow.AddSeconds(8)
do {
    $address=Control '地址和搜索栏' ([System.Windows.Automation.ControlType]::Edit)
    $url=$address.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    if ($url -match 'agentId=([a-f0-9-]+)') { $agentId=$Matches[1]; break }
    Start-Sleep -Milliseconds 150
} while ([DateTime]::UtcNow -lt $deadline)
if (-not $agentId) { throw 'Registration submitted; detail URL pending. Do not repeat submission.' }
$cells=@((Window).FindAll([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::DataItem)) |
    ForEach-Object {$_.Current.Name})
$state=@($cells | Where-Object {$_ -in @('草稿','审核中','已通过','已拒绝','审核未通过')}) | Select-Object -First 1
$aic=@($cells | Where-Object {$_ -match '^1\.2\.156\.'}) | Select-Object -First 1
$observation=[pscustomobject]@{name=$acs.name;version=$acs.version;agent_id=$agentId;status=$state;aic=$aic;submitted_once=$true;observed_at=(Get-Date).ToString('o');source='logged-in Edge UIA actual registration/detail'}
$observation | ConvertTo-Json | Set-Content -LiteralPath $ObservationFile -Encoding utf8
$observation | ConvertTo-Json
