param(
    [Parameter(Mandatory=$true)][string]$AcsFile,
    [Parameter(Mandatory=$true)][long]$WindowHandle,
    [switch]$Save
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$window = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
$acsText = Get-Content -LiteralPath $AcsFile -Raw -Encoding utf8
$acs = $acsText | ConvertFrom-Json
function Find-Control([string]$name, $type) {
    $condition = [System.Windows.Automation.AndCondition]::new(
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$name),
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type))
    $control = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
    if ($null -eq $control) { throw "Registry control not found: $name" }
    return $control
}
$acsControl = Find-Control 'ACS' ([System.Windows.Automation.ControlType]::Edit)
$acsControl.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($acsText)
$deadline = [DateTime]::UtcNow.AddSeconds(5)
do {
    $nameControl = Find-Control '* 名称' ([System.Windows.Automation.ControlType]::Edit)
    $displayName = $nameControl.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    if ($displayName -eq [string]$acs.name) { break }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
if ($displayName -ne [string]$acs.name) { throw 'Registry did not parse the supplied ACS name' }
$entity = Find-Control '否' ([System.Windows.Automation.ControlType]::RadioButton)
$entity.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
if ($Save) {
    $button = Find-Control '保存' ([System.Windows.Automation.ControlType]::Button)
    $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
[pscustomobject]@{name=$acs.name;version=$acs.version;action=$(if ($Save) {'save'} else {'fill'});acs_file=$AcsFile} | ConvertTo-Json
