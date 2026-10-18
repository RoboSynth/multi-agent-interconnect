param(
    [ValidateSet('stdout','kafka')][string]$Mode = 'stdout',
    [string]$LogDirectory = '',
    [string]$KafkaSettings = '',
    [string]$Executable = '',
    [string]$StateRoot = '',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $LogDirectory) { $LogDirectory = Join-Path $ProjectRoot 'runtime/amp-platform' }
if (-not $StateRoot) { $StateRoot = Join-Path $ProjectRoot 'runtime/fluent-bit-state' }
if (-not $CheckOnly -and -not $Executable) {
    $Portable = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'tools/runtime/fluent-bit-5.1.3') -Filter 'fluent-bit.exe' -Recurse)
    if ($Portable.Count -ne 1) { throw 'Specify the official Windows portable fluent-bit.exe with -Executable.' }
    $Executable = $Portable[0].FullName
}
$RenderArgs = @((Join-Path $PSScriptRoot 'render.py'), '--log-directory', $LogDirectory,
    '--state-root', $StateRoot, '--mode', $Mode)
if ($CheckOnly) { $RenderArgs += '--check' }
else { $RenderArgs += @('--executable', $Executable) }
if ($Mode -eq 'kafka') {
    if (-not $KafkaSettings) { throw 'Kafka broker/authentication is unknown: provide confirmed domain-local -KafkaSettings.' }
    $RenderArgs += @('--kafka-settings', $KafkaSettings)
}
& (Join-Path $ProjectRoot '.venv/Scripts/python.exe') @RenderArgs
exit $LASTEXITCODE
