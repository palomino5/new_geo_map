# setup.ps1 — Gestio de l'entorn a Windows
# Us: .\setup.ps1 [accio]
# Accions: setup (per defecte), up, down, logs, build, restart,
#          migrate, migrate-down, shell-db, shell-api,
#          import-municipalities, import-parcels, import-sigpac,
#          download-ndvi, calculate-ndvi, aggregate-ndvi, classify-parcels, pipeline

param([string]$Action = "setup")

function Check-Docker {
    # Usem SilentlyContinue per ignorar warnings de stderr de Docker (ex: DOCKER_INSECURE_NO_IPTABLES_RAW)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    docker info 2>&1 | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev

    if (-not $ok) {
        Write-Host "Docker Desktop no esta corrent. Arrancant..." -ForegroundColor Yellow
        $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerExe) {
            Start-Process $dockerExe
        }
        Write-Host "Esperant Docker Desktop (fins 90s)..." -ForegroundColor DarkGray
        $t = 0
        do {
            Start-Sleep -Seconds 5
            $t += 5
            $ErrorActionPreference = "SilentlyContinue"
            docker info 2>&1 | Out-Null
            $ok = ($LASTEXITCODE -eq 0)
            $ErrorActionPreference = $prev
        } while (-not $ok -and $t -lt 90)

        if (-not $ok) {
            Write-Host "Docker Desktop no ha arrancat. Obre'l manualment i reintenta." -ForegroundColor Red
            exit 1
        }
        Write-Host "Docker Desktop llest." -ForegroundColor Green
    }
}

function DC {
    docker compose @args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: docker compose $args fallo (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Do-Setup {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Creat .env des de .env.example - edita les credencials si cal." -ForegroundColor Yellow
    } else {
        Write-Host ".env ja existeix." -ForegroundColor Green
    }

    Write-Host "`nConstruint imatges Docker..." -ForegroundColor Cyan
    DC build

    Write-Host "`nArrancant serveis..." -ForegroundColor Cyan
    DC up -d

    Write-Host "`nEsperant que PostgreSQL estigui llest..." -ForegroundColor Cyan
    $maxWait = 60
    $t = 0
    $dbHealth = ""
    do {
        Start-Sleep -Seconds 3
        $t += 3
        $containerId = docker compose ps -q db 2>$null
        if ($containerId) {
            $dbHealth = docker inspect --format "{{.State.Health.Status}}" $containerId 2>$null
        }
        Write-Host "  DB ($t s): $dbHealth" -ForegroundColor DarkGray
    } while ($dbHealth -ne "healthy" -and $t -lt $maxWait)

    if ($dbHealth -ne "healthy") {
        Write-Warning "PostgreSQL no ha arrancat en ${maxWait}s. Comprova: docker compose logs db"
        exit 1
    }

    Write-Host "`nExecutant migracions Alembic..." -ForegroundColor Cyan
    DC exec api alembic upgrade head

    Write-Host "`nEntorn llest!" -ForegroundColor Green
    Write-Host "  API:      http://localhost:8000/docs"
    Write-Host "  Frontend: http://localhost:5173"
    Write-Host "  DB:       localhost:5432"
}

function Do-ShellDb {
    $envContent = Get-Content ".env" -ErrorAction Stop
    $user = ($envContent | Select-String "^POSTGRES_USER=(.+)").Matches[0].Groups[1].Value.Trim()
    $db   = ($envContent | Select-String "^POSTGRES_DB=(.+)").Matches[0].Groups[1].Value.Trim()
    docker compose exec db psql -U $user -d $db
}

# --- Dispatcher ---

Check-Docker

if ($Action -eq "setup")                    { Do-Setup }
elseif ($Action -eq "up")                   { DC up -d }
elseif ($Action -eq "down")                 { DC down }
elseif ($Action -eq "logs")                 { docker compose logs -f }
elseif ($Action -eq "build")                { DC build }
elseif ($Action -eq "restart")              { DC restart }
elseif ($Action -eq "migrate")              { DC exec api alembic upgrade head }
elseif ($Action -eq "migrate-down")         { DC exec api alembic downgrade -1 }
elseif ($Action -eq "shell-db")             { Do-ShellDb }
elseif ($Action -eq "shell-api")            { docker compose exec api bash }
elseif ($Action -eq "import-municipalities"){ DC exec api python scripts/import_municipalities.py }
elseif ($Action -eq "import-parcels")       { DC exec api python scripts/import_parcels.py }
elseif ($Action -eq "import-sigpac")        { DC exec api python scripts/import_sigpac.py }
elseif ($Action -eq "download-ndvi")        { DC exec api python scripts/download_sentinel2.py }
elseif ($Action -eq "calculate-ndvi")       { DC exec api python scripts/calculate_ndvi.py }
elseif ($Action -eq "aggregate-ndvi")       { DC exec api python scripts/aggregate_ndvi.py }
elseif ($Action -eq "classify-parcels")     { DC exec api python scripts/classify_parcels.py }
elseif ($Action -eq "pipeline") {
    & $PSCommandPath download-ndvi
    & $PSCommandPath calculate-ndvi
    & $PSCommandPath aggregate-ndvi
    & $PSCommandPath classify-parcels
}
else {
    Write-Host "Accions: setup, up, down, logs, build, restart, migrate, migrate-down, shell-db, shell-api,"
    Write-Host "  import-municipalities, import-parcels, import-sigpac,"
    Write-Host "  download-ndvi, calculate-ndvi, aggregate-ndvi, classify-parcels, pipeline"
}
