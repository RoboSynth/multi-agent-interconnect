param(
    [string]$RegistrationDirectory='D:\AI + 开源\incident-pilot\integration\incident\high-score-registration-20261017',
    [long]$WindowHandle=5445952,
    [switch]$Refresh
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$roles=@('ops','database-backup','coordinator','application','database','verification','onboarding')
$manifest=foreach($role in $roles){
    $acs=Get-Content -LiteralPath "$RegistrationDirectory\$role.submission.acs.json" -Raw -Encoding utf8|ConvertFrom-Json
    $saved=Get-Content -LiteralPath "$RegistrationDirectory\$role.review-observation.json" -Raw -Encoding utf8|ConvertFrom-Json
    [pscustomobject]@{role=$role;name=$acs.name;agent_id=$saved.agent_id}
}
function Window { [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle) }
function Control([string]$name,$type){
    $c=[System.Windows.Automation.AndCondition]::new(
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$name),
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type))
    (Window).FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)
}
if($Refresh){
    $link=Control '我的智能体' ([System.Windows.Automation.ControlType]::Hyperlink)
    if(-not $link){throw 'The logged-in Registry navigation is unavailable'}
    $link.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $refreshButton=Control '刷新' ([System.Windows.Automation.ControlType]::Button)
    $refreshButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Milliseconds 1200
}
$deadline=[DateTime]::UtcNow.AddSeconds(25)
$cellType=[System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::DataItem)
do{
    $rows=foreach($entry in $manifest){
        $item=Control $entry.name ([System.Windows.Automation.ControlType]::DataItem)
        if(-not $item){continue}
        $row=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($item)
        $cells=@($row.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cellType)|ForEach-Object {$_.Current.Name})
        $state=$cells|Where-Object {$_ -in @('草稿','审核中','已通过','已拒绝','审核未通过')}|Select-Object -First 1
        if($state){[pscustomobject]@{role=$entry.role;name=$entry.name;agent_id=$entry.agent_id;status=$state}}
    }
    if(@($rows).Count -eq $manifest.Count){break}
    Start-Sleep -Milliseconds 300
}while([DateTime]::UtcNow -lt $deadline)
if(@($rows).Count -ne $manifest.Count){throw 'Review table is not fully loaded; no status evidence was written'}
$record=[pscustomobject]@{observed_at=(Get-Date).ToString('o');source='logged-in Edge actual Registry list';agents=@($rows)}
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$record|ConvertTo-Json -Depth 6|Set-Content -LiteralPath "$RegistrationDirectory\review-poll-$stamp.json" -Encoding utf8
$record|ConvertTo-Json -Depth 6
