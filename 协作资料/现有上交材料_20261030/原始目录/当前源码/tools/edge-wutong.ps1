param(
    [ValidateSet('list','open-list')]
    [string]$Action = 'list'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$edgeIds = @(Get-Process msedge -ErrorAction SilentlyContinue | ForEach-Object Id)
$tabCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::TabItem)
$window = $null
foreach ($candidate in [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
    [System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.Condition]::TrueCondition)) {
    if ($candidate.Current.ProcessId -notin $edgeIds) { continue }
    $tabs = @($candidate.FindAll([System.Windows.Automation.TreeScope]::Descendants,$tabCondition) |
        Where-Object { $_.Current.Name -match 'ACPs智能体注册' })
    if ($tabs.Count -eq 0) { continue }
    $window = $candidate
    $tabs[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    break
}
if ($null -eq $window) { throw 'Open the ACPs registration page in Edge first' }

if ($Action -eq 'open-list') {
    $linkCondition = [System.Windows.Automation.AndCondition]::new(
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty,'我的智能体'),
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Hyperlink))
    $link = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$linkCondition)
    if ($null -eq $link) { throw 'The My Agents navigation is not visible in this Edge page' }
    $link.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

$items = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)
[PSCustomObject]@{
    browser = 'Microsoft Edge'
    window_handle = $window.Current.NativeWindowHandle
    agents = @($items | Where-Object {
        $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::DataItem -and
        $_.Current.Name -match '^(故障协作.*智能体|任务协调智能体|消息回声智能体)$'
    } | ForEach-Object { $_.Current.Name })
    row_counts = @($items | Where-Object { $_.Current.Name -match '^共.*条$' } |
        ForEach-Object { $_.Current.Name })
} | ConvertTo-Json -Depth 4
