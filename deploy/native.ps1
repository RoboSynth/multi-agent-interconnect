param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [string]$RuntimeFile = '',
    [string]$EnvFile = ''
)
$ErrorActionPreference = 'Stop'
$CallerEnvironment = @{}
function Set-NativeEnvironment([string]$Name, [string]$Value) {
    if (-not $CallerEnvironment.ContainsKey($Name)) {
        $CallerEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
}
try {
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $RuntimeFile) { $RuntimeFile = Join-Path $PSScriptRoot 'native-runtime.json' }
$RuntimeFile = [IO.Path]::GetFullPath($RuntimeFile)
$RunDir = Join-Path $ProjectRoot 'runtime'
if (-not $EnvFile) { $EnvFile = Join-Path $RunDir 'private/application.env' }
if (Test-Path -LiteralPath $EnvFile) {
    foreach ($EnvLine in Get-Content -LiteralPath $EnvFile) {
        if ($EnvLine -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            Set-NativeEnvironment $Matches[1] $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
}
$NginxCandidates = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'tools/runtime') -Filter 'nginx.exe' -Recurse -ErrorAction SilentlyContinue)
$Config = @{
    backend = 'native'; project_root = $ProjectRoot
    postgres_bin = (Join-Path $ProjectRoot 'tools/runtime/pgsql/bin')
    pgdata = (Join-Path $RunDir 'pgdata'); pgport = 55432
    nginx_bin = $(if ($NginxCandidates.Count) { $NginxCandidates[0].FullName } else { Join-Path $ProjectRoot 'tools/runtime/nginx/nginx.exe' })
    nginx_prefix = (Join-Path $RunDir 'nginx')
    app_python = (Join-Path $ProjectRoot '.venv/Scripts/python.exe')
    app_v1_port = 8081; app_v2_port = 8082; order_port = 8088; managed = @{}
}
if (Test-Path -LiteralPath $RuntimeFile) {
    $Saved = Get-Content -LiteralPath $RuntimeFile -Raw | ConvertFrom-Json -AsHashtable
    foreach ($Key in $Saved.Keys) { $Config[$Key] = $Saved[$Key] }
}
if (-not $Config.native_drive -and $Config.nginx_prefix -match '[^\x00-\x7F]') {
    foreach ($CandidateDrive in 'P:','Q:','R:','S:','T:','U:','V:','W:','Y:','Z:') {
        if (-not [IO.Directory]::Exists($CandidateDrive + '\')) {
            $Config.native_drive = $CandidateDrive
            $Config.nginx_prefix = $CandidateDrive + '\runtime\nginx'
            break
        }
    }
    if (-not $Config.native_drive) { throw 'No unused drive letter is available for the project-local ASCII alias.' }
}
if ($Config.native_drive) {
    # Restricted Windows tool sessions have separate DOS-device namespaces.
    # Recreate the project-only ASCII drive alias in this process's logon session.
    $DriveName = $Config.native_drive.TrimEnd(':')
    if (-not [IO.Directory]::Exists($Config.native_drive + '\')) {
        & "$env:SystemRoot\System32\subst.exe" $Config.native_drive $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Unable to create the project-local ASCII drive alias.' }
    }
    & $Config.app_python -c 'import os,sys; sys.exit(0 if os.path.samefile(sys.argv[1], sys.argv[2]) else 2)' ($Config.native_drive + '\') $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw 'The configured ASCII drive alias belongs to another directory.' }
    if (-not (Get-PSDrive -Name $DriveName -ErrorAction SilentlyContinue)) {
        New-PSDrive -Name $DriveName -PSProvider FileSystem -Root ($Config.native_drive + '\') -Scope Script | Out-Null
    }
}
function Get-ManagedApp([string]$Version) {
    $PidValue = $Config.managed[$Version]
    if (-not $PidValue) { return $null }
    $RecordJson = & $Config.app_python (Join-Path $ProjectRoot 'business/native_process.py') --pid $PidValue --script run_app.py --version $Version
    if ($LASTEXITCODE -ne 0) { throw "Unable to validate managed app $Version PID $PidValue." }
    return ($RecordJson | ConvertFrom-Json)
}
function Save-Runtime {
    $Config | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $RuntimeFile -Encoding utf8
}
if ($Action -eq 'status') {
    & (Join-Path $Config.postgres_bin 'pg_ctl.exe') status -D $Config.pgdata
    foreach ($Version in 'v1','v2') {
        $AppProcess = Get-ManagedApp $Version
        [pscustomobject]@{ version = $Version; running = [bool]$AppProcess; pid = $Config.managed[$Version] }
    }
    exit 0
}
if ($Action -eq 'stop') {
    foreach ($Version in 'v1','v2') {
        $RegisteredAppPid = $Config.managed[$Version]
        if ($RegisteredAppPid) {
            $AppPort = $Config["app_$($Version)_port"]
            & $Config.app_python (Join-Path $ProjectRoot 'business/native_process.py') --pid $RegisteredAppPid --script run_app.py --version $Version --port $AppPort --python-executable $Config.app_python --app-family --terminate | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Unable to stop managed app $Version." }
        }
        $Config.managed.Remove($Version)
    }
    if (Test-Path -LiteralPath (Join-Path $Config.nginx_prefix 'logs/nginx.pid')) {
        & $Config.nginx_bin -p ($Config.nginx_prefix.Replace([char]92,[char]47) + '/') -s quit
    }
    & (Join-Path $Config.postgres_bin 'pg_ctl.exe') stop -D $Config.pgdata -m fast
    Save-Runtime
    exit 0
}
foreach ($SecretName in 'PGPASSWORD','APP_ADMIN_TOKEN') {
    if (-not [Environment]::GetEnvironmentVariable($SecretName)) { throw "Set application-domain environment variable $SecretName before starting." }
}
if (-not (Test-Path -LiteralPath (Join-Path $Config.pgdata 'PG_VERSION'))) {
    throw 'Initialize the project-local PostgreSQL data directory and orders schema first. See deploy/README.md.'
}
foreach ($Executable in $Config.app_python, $Config.nginx_bin, (Join-Path $Config.postgres_bin 'pg_ctl.exe')) {
    if (-not (Test-Path -LiteralPath $Executable)) { throw "Required local executable is missing: $Executable" }
}
New-Item -ItemType Directory -Path $RunDir,(Join-Path $Config.nginx_prefix 'conf'),(Join-Path $Config.nginx_prefix 'logs'),(Join-Path $Config.nginx_prefix 'temp') -Force | Out-Null
& (Join-Path $Config.postgres_bin 'pg_ctl.exe') status -D $Config.pgdata *> $null
if ($LASTEXITCODE -ne 0) {
    Save-Runtime
    # pg_ctl's CreateRestrictedToken cannot nest in the desktop sandbox.
    & $Config.app_python (Join-Path $ProjectRoot 'business/native_postgres.py') --runtime $RuntimeFile
    if ($LASTEXITCODE -ne 0) { throw 'Project PostgreSQL failed to start under the current token.' }
}
Set-NativeEnvironment 'PGHOST' '127.0.0.1'
Set-NativeEnvironment 'PGPORT' ([string]$Config.pgport)
Set-NativeEnvironment 'PGDATABASE' 'orders'
Set-NativeEnvironment 'PGUSER' 'orders_app'
foreach ($Version in 'v1','v2') {
    if (-not (Get-ManagedApp $Version)) {
        $AppPort = $Config["app_$($Version)_port"]
        $AppArgs = @('"' + (Join-Path $ProjectRoot 'business/run_app.py') + '"', '--version', $Version, '--port', [string]$AppPort)
        $AppProcess = Start-Process -FilePath $Config.app_python -ArgumentList $AppArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $RunDir "$Version.stdout.log") -RedirectStandardError (Join-Path $RunDir "$Version.stderr.log")
        $Config.managed[$Version] = $AppProcess.Id
        Save-Runtime
    }
}
$NginxConfig = @'
events { worker_connections 512; }
http {
    access_log logs/access.log;
    error_log logs/error.log;
    server {
        listen 127.0.0.1:ORDER_PORT;
        include route.conf;
        location /admin/ { return 403; }
        location / {
            proxy_pass http://$order_upstream;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_connect_timeout 2s;
            proxy_read_timeout 5s;
            proxy_next_upstream off;
        }
    }
}
'@
$NginxConfig.Replace('ORDER_PORT', [string]$Config.order_port) | Set-Content -LiteralPath (Join-Path $Config.nginx_prefix 'conf/nginx.conf') -Encoding ascii
$RouteFile = Join-Path $Config.nginx_prefix 'conf/route.conf'
if (-not (Test-Path -LiteralPath $RouteFile)) {
    ('set $order_upstream 127.0.0.1:' + $Config.app_v2_port + ';') | Set-Content -LiteralPath $RouteFile -Encoding ascii
}
$NginxPrefix = $Config.nginx_prefix.Replace([char]92,[char]47) + '/'
& $Config.nginx_bin -p $NginxPrefix -t
if ($LASTEXITCODE -ne 0) { throw 'Native nginx configuration is invalid.' }
$NginxPidPath = Join-Path $Config.nginx_prefix 'logs/nginx.pid'
$ExistingNginxPid = ''
if (Test-Path -LiteralPath $NginxPidPath) {
    $PidContent = Get-Content -LiteralPath $NginxPidPath -Raw
    if ($PidContent) { $ExistingNginxPid = $PidContent.Trim() }
}
if ($ExistingNginxPid -match '^\d+$' -and (Get-Process -Id ([int]$ExistingNginxPid) -ErrorAction SilentlyContinue)) {
    & $Config.nginx_bin -p $NginxPrefix -s reload
} else {
    Start-Process -FilePath $Config.nginx_bin -ArgumentList @('-p', ('"' + $NginxPrefix + '"')) -WorkingDirectory $Config.nginx_prefix -WindowStyle Hidden
}
Save-Runtime
foreach ($ProbePort in $Config.app_v1_port,$Config.app_v2_port,$Config.order_port) {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        try { $Response = Invoke-RestMethod -Uri "http://127.0.0.1:$ProbePort/ready" -TimeoutSec 2; if (($Response.ok -eq $true) -and ($ProbePort -ne $Config.order_port -or $Response.api_version -eq 'v2')) { $Ready = $true; break } } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $Ready) {
        if ($ProbePort -eq $Config.order_port) {
            throw "Public entry on local port $ProbePort must be ready with api_version=v2. Check the existing Nginx route.conf and use the normal scenario restore when appropriate; start preserves existing routes."
        }
        throw "Service on local port $ProbePort did not become ready. Inspect runtime/*.stderr.log."
    }
}
Write-Output "Local order target ready at http://127.0.0.1:$($Config.order_port); runtime configuration: $RuntimeFile"
} finally {
    foreach ($Name in $CallerEnvironment.Keys) {
        if ($null -eq $CallerEnvironment[$Name]) {
            Remove-Item -LiteralPath ("Env:" + $Name) -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($Name, $CallerEnvironment[$Name], 'Process')
        }
    }
}
