param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '.env'),
    [string]$ProjectName = 'incident-pilot',
    [string]$WslDistro = 'Ubuntu-22.04',
    [switch]$Agents,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
if ($ProjectName -notmatch '^[a-z0-9][a-z0-9_-]*$') { throw 'Invalid Compose project name.' }
$Docker = Get-Command docker -ErrorAction SilentlyContinue
if ($Docker) {
    $Executable = $Docker.Source
    $Prefix = @()
    $ComposeFile = Join-Path $PSScriptRoot 'compose.yml'
    $AgentsFile = Join-Path $PSScriptRoot 'agents.yml'
} else {
    $Executable = (Get-Command wsl.exe -ErrorAction Stop).Source
    $Prefix = @('-d', $WslDistro, '--exec', 'docker')
    function Convert-ToWslPath([string]$Value) {
        $Full = [IO.Path]::GetFullPath($Value)
        if ($Full -notmatch '^([a-zA-Z]):[\\/]') { throw 'WSL deployment requires a local drive path.' }
        '/mnt/' + $Matches[1].ToLowerInvariant() + $Full.Substring(2).Replace('\', '/')
    }
    $EnvFile = Convert-ToWslPath $EnvFile
    $ComposeFile = Convert-ToWslPath (Join-Path $PSScriptRoot 'compose.yml')
    $AgentsFile = Convert-ToWslPath (Join-Path $PSScriptRoot 'agents.yml')
}
$Compose = @('compose', '-p', $ProjectName, '--env-file', $EnvFile, '-f', $ComposeFile)
if ($Agents) { $Compose += @('-f', $AgentsFile, '--profile', 'agents') }
& $Executable @Prefix @Compose config --quiet
if ($LASTEXITCODE) { throw 'Compose configuration failed.' }
if ($ValidateOnly) { Write-Output "Compose project $ProjectName configuration passed."; return }
$RouteDirectory = Join-Path $PSScriptRoot 'nginx/runtime'
$RouteFile = Join-Path $RouteDirectory 'route.conf'
if (-not (Test-Path -LiteralPath $RouteFile)) {
    New-Item -ItemType Directory -Path $RouteDirectory -Force | Out-Null
    [IO.File]::Copy((Join-Path $PSScriptRoot 'nginx/route.default.conf'), $RouteFile, $false)
}
& $Executable @Prefix @Compose up -d --build --wait
if ($LASTEXITCODE) { throw 'Compose startup failed.' }
Write-Output "Compose project $ProjectName started."
