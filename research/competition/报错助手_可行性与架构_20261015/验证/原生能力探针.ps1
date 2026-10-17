param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($root) | Out-Null
$results = [ordered]@{}
$watcher = $null
$eventWatcher = $null
$subscription = $null
try {
    $watcher = [IO.FileSystemWatcher]::new($root, '*.log')
    $watcher.NotifyFilter = [IO.NotifyFilters]::FileName -bor [IO.NotifyFilters]::LastWrite
    $eventName = 'ErrorAssistantFeasibility.' + [Guid]::NewGuid().ToString('N')
    $subscription = Register-ObjectEvent -InputObject $watcher -EventName Created -SourceIdentifier $eventName
    $watcher.EnableRaisingEvents = $true
    $target = Join-Path $root ('synthetic-' + [Guid]::NewGuid().ToString('N') + '.log')
    [IO.File]::WriteAllText($target, 'SYNTHETIC_ERROR: controlled file watcher probe')
    $received = Wait-Event -SourceIdentifier $eventName -Timeout 5
    $results.file_watcher = [ordered]@{
        passed = ($null -ne $received)
        scope = 'Only the synthetic log created in the requested probe directory'
    }
} catch {
    $results.file_watcher = @{passed=$false; error=$_.Exception.Message}
} finally {
    if ($null -ne $watcher) { $watcher.EnableRaisingEvents=$false; $watcher.Dispose() }
    if ($null -ne $subscription) {
        Unregister-Event -SourceIdentifier $eventName -ErrorAction SilentlyContinue
        Get-Event -SourceIdentifier $eventName -ErrorAction SilentlyContinue | Remove-Event
        Remove-Job -Id $subscription.Id -Force -ErrorAction SilentlyContinue
    }
}
try {
    $query = [Diagnostics.Eventing.Reader.EventLogQuery]::new('Application', [Diagnostics.Eventing.Reader.PathType]::LogName)
    $eventWatcher = [Diagnostics.Eventing.Reader.EventLogWatcher]::new($query)
    $eventWatcher.Enabled = $true
    $results.event_log_subscription = [ordered]@{
        passed = $eventWatcher.Enabled
        scope = 'Future Application events subscription registration only; no log contents exported and no event injected'
    }
} catch {
    $results.event_log_subscription = @{passed=$false; error=$_.Exception.Message}
} finally {
    if ($null -ne $eventWatcher) { $eventWatcher.Enabled=$false; $eventWatcher.Dispose() }
}
try {
    $uiaType = [Type]::GetTypeFromCLSID([Guid]'FF48DBA4-60EF-4201-AA87-54103EEF594E')
    $uia = [Activator]::CreateInstance($uiaType)
    $results.ui_automation_activation = [ordered]@{
        passed = ($null -ne $uia)
        scope = 'COM activation only; no user windows inspected and no GUI error recognition tested'
    }
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($uia) | Out-Null
} catch {
    $results.ui_automation_activation = @{passed=$false; error=$_.Exception.Message}
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$results.process_context = @{
    elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    powershell = $PSVersionTable.PSVersion.ToString()
}
$json = $results | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'native-results.json'), $json, [Text.UTF8Encoding]::new($false))
$json
