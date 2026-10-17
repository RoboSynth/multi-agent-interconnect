param(
    [Parameter(Mandatory=$true)][string]$AgentName,
    [ValidateSet('详情','提交审核')][string]$Action = '详情',
    [long]$WindowHandle = 5445952
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$window=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
$nameCondition=[System.Windows.Automation.AndCondition]::new(
    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$AgentName),
    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::DataItem))
$cell=$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$nameCondition)
if($null -eq $cell){throw 'The exact agent row is not visible'}
$buttonCondition=[System.Windows.Automation.AndCondition]::new(
    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$Action),
    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
$scope=$cell
for($depth=0;$depth -lt 7;$depth++) {
    $buttons=$scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,$buttonCondition)
    if($buttons.Count -eq 1){
        $buttons[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        [pscustomobject]@{agent=$AgentName;action=$Action;matched_exact_row=$true}|ConvertTo-Json
        exit 0
    }
    if($buttons.Count -gt 1){throw 'Agent row action is ambiguous; no action was invoked'}
    $scope=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($scope)
    if($null -eq $scope){break}
}
throw 'No unique action found within the exact agent row'
