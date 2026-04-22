param(
  [Parameter(Mandatory = $false)][int]$PostgresHostPort,
  [Parameter(Mandatory = $false)][int]$EmqxMqttHostPort
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Native {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $false)][string[]]$Arguments = @(),
    [Parameter(Mandatory = $false)][string]$ErrorMessage = "Command failed"
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$ErrorMessage (exit code: $LASTEXITCODE): $FilePath $($Arguments -join ' ')"
  }
}

function Get-PortOwnerInfo {
  param(
    [Parameter(Mandatory = $true)][int]$Port
  )

  try {
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop
    if (-not $connections) {
      return $null
    }

    $owners = $connections |
      Select-Object -ExpandProperty OwningProcess -Unique |
      ForEach-Object {
        try {
          $p = Get-Process -Id $_ -ErrorAction Stop
          "$($p.ProcessName) (PID $_)"
        } catch {
          "PID $_"
        }
      }

    return ($owners -join ", ")
  } catch {
    return $null
  }
}

function Test-LocalPortInUse {
  param(
    [Parameter(Mandatory = $true)][int]$Port
  )

  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
    $listener.Start()
    $listener.Stop()
    return $false
  } catch {
    return $true
  }
}

function Get-EnvIntOrDefault {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][int]$Default
  )

  $value = [Environment]::GetEnvironmentVariable($Name)
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $Default
  }

  $parsed = 0
  if ([int]::TryParse($value, [ref]$parsed)) {
    return $parsed
  }

  return $Default
}

Write-Host "Restarting AeroCommand dev stack..." -ForegroundColor Cyan

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
  Write-Host "Docker CLI not found. Start Docker Desktop and ensure it is on PATH." -ForegroundColor Red
  Write-Host "Expected path: C:\Program Files\Docker\Docker\resources\bin" -ForegroundColor Yellow
  exit 1
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $repoRoot "docker-compose.yml"
if (-not (Test-Path $composeFile)) {
  throw "Expected compose file not found: $composeFile"
}

if ($PostgresHostPort) {
  $env:POSTGRES_HOST_PORT = "$PostgresHostPort"
  Write-Host "Using POSTGRES_HOST_PORT=$PostgresHostPort for this run" -ForegroundColor Yellow
}

if ($EmqxMqttHostPort) {
  $env:EMQX_MQTT_HOST_PORT = "$EmqxMqttHostPort"
  Write-Host "Using EMQX_MQTT_HOST_PORT=$EmqxMqttHostPort for this run" -ForegroundColor Yellow
}

# If the default Docker config dir isn't writable (common on Windows when permissions get messed up),
# run this script with a temp DOCKER_CONFIG to avoid config.json/buildx lock 'Access is denied' errors.
$defaultDockerConfigDir = Join-Path $HOME ".docker"
try {
  if (-not (Test-Path $defaultDockerConfigDir)) {
    New-Item -ItemType Directory -Path $defaultDockerConfigDir -Force | Out-Null
  }
  $probeFile = Join-Path $defaultDockerConfigDir ".aerocommand_write_probe"
  Set-Content -Path $probeFile -Value "probe" -Encoding ascii -ErrorAction Stop
  Remove-Item -Path $probeFile -Force -ErrorAction SilentlyContinue
} catch {
  $tempDockerConfigDir = Join-Path $env:TEMP "aerocommand-docker-config"
  New-Item -ItemType Directory -Path $tempDockerConfigDir -Force | Out-Null
  $env:DOCKER_CONFIG = $tempDockerConfigDir
  Write-Host "Default Docker config is not accessible: $defaultDockerConfigDir" -ForegroundColor Yellow
  Write-Host "Using temporary DOCKER_CONFIG for this run: $tempDockerConfigDir" -ForegroundColor Yellow
}

$scriptFailed = $false
$failureMessage = $null

Push-Location $repoRoot
try {
  # Prefer 'docker compose', fallback to legacy 'docker-compose' if needed.
  $useLegacyCompose = $false
  try {
    Invoke-Native -FilePath "docker" -Arguments @("compose", "version") -ErrorMessage "Docker Compose v2 is not available"
  } catch {
    $legacy = Get-Command docker-compose -ErrorAction SilentlyContinue
    if (-not $legacy) {
      throw "Neither 'docker compose' (v2) nor 'docker-compose' (v1) is available. Update Docker Desktop or install docker-compose."
    }
    $useLegacyCompose = $true
  }

  if ($useLegacyCompose) {
    Invoke-Native -FilePath "docker-compose" -Arguments @("-f", $composeFile, "down") -ErrorMessage "Failed to stop dev stack"

    $portsToCheck = @(
      @{ Name = "Postgres"; Port = (Get-EnvIntOrDefault -Name "POSTGRES_HOST_PORT" -Default 5432); Hint = ".\\scripts\\restart-dev.ps1 -PostgresHostPort 5433" },
      @{ Name = "Mongo"; Port = 27017; Hint = "Stop the service using the port or adjust docker-compose.yml" },
      @{ Name = "EMQX MQTT"; Port = (Get-EnvIntOrDefault -Name "EMQX_MQTT_HOST_PORT" -Default 1883); Hint = ".\\scripts\\restart-dev.ps1 -EmqxMqttHostPort 1884" },
      @{ Name = "EMQX WS"; Port = (Get-EnvIntOrDefault -Name "EMQX_WS_HOST_PORT" -Default 8083); Hint = "`$env:EMQX_WS_HOST_PORT=8084" },
      @{ Name = "EMQX Dashboard"; Port = (Get-EnvIntOrDefault -Name "EMQX_DASHBOARD_HOST_PORT" -Default 18083); Hint = "`$env:EMQX_DASHBOARD_HOST_PORT=18084" },
      @{ Name = "API"; Port = 8000; Hint = "Stop the service using the port or adjust docker-compose.yml" },
      @{ Name = "Dashboard"; Port = 3000; Hint = "Stop the service using the port or adjust docker-compose.yml" }
    )

    foreach ($p in $portsToCheck) {
      if (Test-LocalPortInUse -Port $p.Port) {
        $ownerInfo = Get-PortOwnerInfo -Port $p.Port
        $msg = "Port $($p.Port) is already in use, so '$($p.Name)' can't bind."
        if ($ownerInfo) {
          $msg += " Owner: $ownerInfo"
        }
        if ($p.Hint) {
          $msg += " `nTry: $($p.Hint)"
        }
        throw $msg
      }
    }

    Invoke-Native -FilePath "docker-compose" -Arguments @("-f", $composeFile, "up", "-d", "--build") -ErrorMessage "Failed to start dev stack"
  } else {
    Invoke-Native -FilePath "docker" -Arguments @("compose", "-f", $composeFile, "down") -ErrorMessage "Failed to stop dev stack"

    $portsToCheck = @(
      @{ Name = "Postgres"; Port = (Get-EnvIntOrDefault -Name "POSTGRES_HOST_PORT" -Default 5432); Hint = ".\\scripts\\restart-dev.ps1 -PostgresHostPort 5433" },
      @{ Name = "Mongo"; Port = 27017; Hint = "Stop the service using the port or adjust docker-compose.yml" },
      @{ Name = "EMQX MQTT"; Port = (Get-EnvIntOrDefault -Name "EMQX_MQTT_HOST_PORT" -Default 1883); Hint = ".\\scripts\\restart-dev.ps1 -EmqxMqttHostPort 1884" },
      @{ Name = "EMQX WS"; Port = (Get-EnvIntOrDefault -Name "EMQX_WS_HOST_PORT" -Default 8083); Hint = "`$env:EMQX_WS_HOST_PORT=8084" },
      @{ Name = "EMQX Dashboard"; Port = (Get-EnvIntOrDefault -Name "EMQX_DASHBOARD_HOST_PORT" -Default 18083); Hint = "`$env:EMQX_DASHBOARD_HOST_PORT=18084" },
      @{ Name = "API"; Port = 8000; Hint = "Stop the service using the port or adjust docker-compose.yml" },
      @{ Name = "Dashboard"; Port = 3000; Hint = "Stop the service using the port or adjust docker-compose.yml" }
    )

    foreach ($p in $portsToCheck) {
      if (Test-LocalPortInUse -Port $p.Port) {
        $ownerInfo = Get-PortOwnerInfo -Port $p.Port
        $msg = "Port $($p.Port) is already in use, so '$($p.Name)' can't bind."
        if ($ownerInfo) {
          $msg += " Owner: $ownerInfo"
        }
        if ($p.Hint) {
          $msg += " `nTry: $($p.Hint)"
        }
        throw $msg
      }
    }

    Invoke-Native -FilePath "docker" -Arguments @("compose", "-f", $composeFile, "up", "-d", "--build") -ErrorMessage "Failed to start dev stack"
  }
} catch {
  $scriptFailed = $true
  $failureMessage = $_.Exception.Message
} finally {
  Pop-Location
}

if ($scriptFailed) {
  Write-Host "" 
  Write-Host "Failed to restart dev stack." -ForegroundColor Red
  if ($failureMessage) {
    Write-Host $failureMessage -ForegroundColor Red
  }

  $bindPortMatch = $null
  if ($failureMessage) {
    $bindPortMatch = [regex]::Match($failureMessage, 'Bind for 0\.0\.0\.0:(\d+) failed: port is already allocated')
  }
  if ($bindPortMatch -and $bindPortMatch.Success) {
    $conflictPort = [int]$bindPortMatch.Groups[1].Value
    $ownerInfo = Get-PortOwnerInfo -Port $conflictPort
    Write-Host "" 
    Write-Host "Port $conflictPort is already in use." -ForegroundColor Yellow
    if ($ownerInfo) {
      Write-Host "$conflictPort appears owned by: $ownerInfo" -ForegroundColor Yellow
    }

    if ($conflictPort -eq 5432) {
      Write-Host "Try: .\\scripts\\restart-dev.ps1 -PostgresHostPort 5433" -ForegroundColor Yellow
    } elseif ($conflictPort -eq 1883) {
      Write-Host "Try: .\\scripts\\restart-dev.ps1 -EmqxMqttHostPort 1884" -ForegroundColor Yellow
      Write-Host "(or set `$env:EMQX_MQTT_HOST_PORT=1884 before running)" -ForegroundColor Yellow
    } else {
      Write-Host "Stop the service using that port, or adjust docker-compose.yml / env var overrides." -ForegroundColor Yellow
    }
  }

  exit 1
}

Write-Host "Dev stack restarted." -ForegroundColor Green
Write-Host "Dashboard: http://localhost:3000" -ForegroundColor Green
Write-Host "API:       http://localhost:8000 (health: /health/ready)" -ForegroundColor Green
Write-Host "EMQX:      http://localhost:18083 (admin / aerocommand_emqx_admin)" -ForegroundColor Green
