# One-time MySQL setup for this project ONLY. You run this yourself.
#  - creates database  skin_ai_db (utf8mb4)
#  - creates user      skin_ai_app@localhost      SELECT/INSERT/UPDATE/DELETE on skin_ai_db.* (used by the app)
#  - creates user      skin_ai_migrate@localhost  schema rights on skin_ai_db.* (used only by db_upgrade.ps1)
# Passwords for the two new users are generated here and written to .env (git-ignored); they are never printed.
# The MySQL root password is typed by YOU into the mysql client's own hidden prompt.
# Nothing else on the server (other databases, users, services) is touched. Safe to re-run.
param([string]$MysqlExe = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe',
      [string]$AdminUser = 'root', [int]$Port = 3306)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root '.env'
if (-not (Test-Path $MysqlExe)) { throw "mysql.exe not found at $MysqlExe (use -MysqlExe)" }
if (-not (Test-Path $EnvFile)) { throw ".env not found. Copy .env.example to .env first." }

function Get-EnvMap { $m = [ordered]@{}; foreach ($l in [IO.File]::ReadAllLines($EnvFile)) { if ($l -match '^\s*([A-Z_]+)\s*=(.*)$') { $m[$Matches[1]] = $Matches[2] } }; $m }
function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = [Collections.Generic.List[string]]([IO.File]::ReadAllLines($EnvFile))
    $i = $lines.FindIndex([Predicate[string]]{ param($l) $l -match "^\s*$Key\s*=" })
    if ($i -ge 0) { $lines[$i] = "$Key=$Value" } else { $lines.Add("$Key=$Value") }
    [IO.File]::WriteAllText($EnvFile, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
}
function New-Secret { $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ([Convert]::ToBase64String($b) -replace '[+/=]', 'x') }

$envMap = Get-EnvMap
$db  = if ($envMap['DB_NAME']) { $envMap['DB_NAME'] } else { 'skin_ai_db' }
$app = if ($envMap['DB_USER']) { $envMap['DB_USER'] } else { 'skin_ai_app' }
$mig = if ($envMap['DB_MIGRATE_USER']) { $envMap['DB_MIGRATE_USER'] } else { 'skin_ai_migrate' }
foreach ($name in $db, $app, $mig) { if ($name -notmatch '^[A-Za-z0-9_]{1,32}$') { throw "Unsafe identifier: $name" } }

$appPwd = if ($envMap['DB_PASSWORD']) { $envMap['DB_PASSWORD'] } else { New-Secret }
$migPwd = if ($envMap['DB_MIGRATE_PASSWORD']) { $envMap['DB_MIGRATE_PASSWORD'] } else { New-Secret }

$sql = @"
CREATE DATABASE IF NOT EXISTS ``$db`` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '$app'@'localhost' IDENTIFIED BY '$appPwd';
ALTER USER '$app'@'localhost' IDENTIFIED BY '$appPwd';
CREATE USER IF NOT EXISTS '$mig'@'localhost' IDENTIFIED BY '$migPwd';
ALTER USER '$mig'@'localhost' IDENTIFIED BY '$migPwd';
GRANT SELECT, INSERT, UPDATE, DELETE ON ``$db``.* TO '$app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES ON ``$db``.* TO '$mig'@'localhost';
FLUSH PRIVILEGES;
SELECT CONCAT('OK: database ', '$db', ' and users ready') AS result;
"@

Write-Host "Connecting to MySQL on 127.0.0.1:$Port as '$AdminUser'. Enter that account's password at the prompt."
# SQL goes through stdin (not the command line), so the generated passwords never appear in the process list.
$sql | & $MysqlExe --host=127.0.0.1 --port=$Port --user=$AdminUser -p --batch --skip-column-names
if ($LASTEXITCODE -ne 0) { throw "mysql exited with code $LASTEXITCODE; nothing was written to .env" }

Set-EnvValue 'DB_NAME' $db
Set-EnvValue 'DB_USER' $app
Set-EnvValue 'DB_PASSWORD' $appPwd
Set-EnvValue 'DB_MIGRATE_USER' $mig
Set-EnvValue 'DB_MIGRATE_PASSWORD' $migPwd
Write-Host "Saved credentials for '$app' and '$mig' to .env (not displayed). Next: .\scripts\db_upgrade.ps1"
