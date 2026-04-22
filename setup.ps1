# setup.ps1 — Configura l'entorn complet a Windows
# Ús: .\setup.ps1
# O per a accions individuals: .\setup.ps1 up | down | logs | migrate | shell-db | shell-api

param(
    [string]$Action = "setup"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Comprova que Docker Desktop estigui corrent
$dockerOk = docker info 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Docker Desktop no està corrent. Arrancant..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    Write-Host "   Esperant que Docker Desktop arranqui (fins a 60 s)..." -ForegroundColor DarkGray
    $waited = 0
    do {
        Start-Sleep -Seconds 5
        $waited += 5
        $dockerOk = docker info 2>$null
    } while ($LASTEXITCODE -ne 0 -and $waited -lt 60)

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker Desktop no ha arrancat. Obre'l manualment i torna a executar .\setup.ps1"
        exit 1
    }
    Write-Host "✓ Docker Desktop llest" -ForegroundColor Green
}

function Invoke-DockerCompose {
    docker compose @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed (exit $LASTEXITCODE)" }
}

switch ($Action) {

    "setup" {
        # 1. Crear .env si no existeix
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Host "✓ Creat .env des de .env.example — edita les credencials si cal" -ForegroundColor Yellow
        } else {
            Write-Host "✓ .env ja existeix" -ForegroundColor Green
        }

        # 2. Build
        Write-Host "`n→ Construint imatges Docker..." -ForegroundColor Cyan
        Invoke-DockerCompose build

        # 3. Arrancar serveis
        Write-Host "`n→ Arrancant serveis..." -ForegroundColor Cyan
        Invoke-DockerCompose up -d

        # 4. Esperar que postgres estigui ready
        Write-Host "`n→ Esperant que PostgreSQL estigui llest..." -ForegroundColor Cyan
        $maxWait = 60
        $waited = 0
        do {
            Start-Sleep -Seconds 3
            $waited += 3
            $health = docker inspect --format="{{.State.Health.Status}}" (docker compose ps -q db) 2>$null
            Write-Host "  DB health: $health ($waited s)" -ForegroundColor DarkGray
        } while ($health -ne "healthy" -and $waited -lt $maxWait)

        if ($health -ne "healthy") {
            Write-Warning "PostgreSQL no ha arrancat en ${maxWait}s. Comprova: docker compose logs db"
            exit 1
        }

        # 5. Migracions
        Write-Host "`n→ Executant migracions Alembic..." -ForegroundColor Cyan
        Invoke-DockerCompose exec api alembic upgrade head

        Write-Host "`n✅ Entorn llest!" -ForegroundColor Green
        Write-Host "   API:      http://localhost:8000/docs" -ForegroundColor White
        Write-Host "   Frontend: http://localhost:5173" -ForegroundColor White
        Write-Host "   DB:       localhost:5432" -ForegroundColor White
    }

    "up"      { Invoke-DockerCompose up -d }
    "down"    { Invoke-DockerCompose down }
    "logs"    { docker compose logs -f }
    "build"   { Invoke-DockerCompose build }
    "restart" { Invoke-DockerCompose restart }

    "migrate" {
        Invoke-DockerCompose exec api alembic upgrade head
    }
    "migrate-down" {
        Invoke-DockerCompose exec api alembic downgrade -1
    }

    "shell-db" {
        $user = (Get-Content .env | Select-String "POSTGRES_USER=(.+)" | ForEach-Object { $_.Matches[0].Groups[1].Value })
        $db   = (Get-Content .env | Select-String "POSTGRES_DB=(.+)"   | ForEach-Object { $_.Matches[0].Groups[1].Value })
        docker compose exec db psql -U $user -d $db
    }
    "shell-api" {
        docker compose exec api bash
    }

    "import-municipalities" { Invoke-DockerCompose exec api python scripts/import_municipalities.py }
    "import-parcels"        { Invoke-DockerCompose exec api python scripts/import_parcels.py }
    "import-sigpac"         { Invoke-DockerCompose exec api python scripts/import_sigpac.py }
    "download-ndvi"         { Invoke-DockerCompose exec api python scripts/download_sentinel2.py }
    "calculate-ndvi"        { Invoke-DockerCompose exec api python scripts/calculate_ndvi.py }
    "aggregate-ndvi"        { Invoke-DockerCompose exec api python scripts/aggregate_ndvi.py }
    "classify-parcels"      { Invoke-DockerCompose exec api python scripts/classify_parcels.py }

    "pipeline" {
        & $PSCommandPath download-ndvi
        & $PSCommandPath calculate-ndvi
        & $PSCommandPath aggregate-ndvi
        & $PSCommandPath classify-parcels
    }

    default {
        Write-Host "Accions disponibles: setup, up, down, logs, build, restart, migrate, migrate-down,"
        Write-Host "  shell-db, shell-api, import-municipalities, import-parcels, import-sigpac,"
        Write-Host "  download-ndvi, calculate-ndvi, aggregate-ndvi, classify-parcels, pipeline"
    }
}
