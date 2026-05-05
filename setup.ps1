# setup.ps1 — Gestio de l'entorn a Windows
# Us: .\setup.ps1 [accio]
# Accions: setup (per defecte), up, down, logs, build, restart,
#          migrate, migrate-down, shell-db, shell-api,
#          import-municipalities, import-parcels, import-sigpac,
#          download-sentinel2, calculate-ndvi, aggregate-ndvi, classify-parcels, pipeline
#
# Exemples amb parametres opcionals:
#   .\setup.ps1 download-sentinel2
#   .\setup.ps1 download-sentinel2 -Start 2024-01-01 -End 2024-12-31 -MaxCloud 20
#   .\setup.ps1 download-catastro -Name "Vic"
#   .\setup.ps1 download-catastro -Code 08001

param(
    [string]$Action = "setup",
    [string]$Start = "2024-01-01",
    [string]$End = "2024-12-31",
    [float]$MaxCloud = 20.0,
    [string]$Name = "",
    [string]$Code = ""
)

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

function Get-CopernicusCreds {
    $envContent = Get-Content ".env" -ErrorAction Stop
    $userMatch = $envContent | Select-String "^COPERNICUS_USER=(.+)"
    $passMatch = $envContent | Select-String "^COPERNICUS_PASS=(.+)"
    $user = if ($userMatch) { $userMatch.Matches[0].Groups[1].Value.Trim().Trim('"') } else { "" }
    $pass = if ($passMatch) { $passMatch.Matches[0].Groups[1].Value.Trim().Trim('"') } else { "" }
    if (-not $user -or -not $pass) {
        Write-Host "ERROR: Cal definir COPERNICUS_USER i COPERNICUS_PASS al fitxer .env" -ForegroundColor Red
        exit 1
    }
    return $user, $pass
}

function Do-DownloadSentinel2 {
    $user, $pass = Get-CopernicusCreds
    Write-Host "Descarregant imatges Sentinel-2 ($Start a $End, max $MaxCloud% nuvols)..." -ForegroundColor Cyan
    docker compose exec api python scripts/download_sentinel2.py `
        --start $Start --end $End --max-cloud $MaxCloud `
        --username $user --password $pass
}

function Do-DownloadCatastro {
    if ($Name) {
        Write-Host "Descarregant parcel·les del Catastro per: $Name..." -ForegroundColor Cyan
        $nameArgs = $Name -split ","
        docker compose exec api python scripts/download_catastro.py --name @nameArgs
    } elseif ($Code) {
        Write-Host "Descarregant parcel·les del Catastro per codi INE: $Code..." -ForegroundColor Cyan
        $codeArgs = $Code -split ","
        docker compose exec api python scripts/download_catastro.py --code @codeArgs
    } else {
        Write-Host "AVÍS: Indica un municipi amb -Name 'Vic' o -Code 08001" -ForegroundColor Yellow
        Write-Host "Per descarregar TOTS els municipis de Catalunya:"
        Write-Host "  .\setup.ps1 download-catastro-all" -ForegroundColor Gray
    }
}

function Do-DownloadCatastroAll {
    Write-Host "Descarregant parcel·les de TOTS els municipis de Catalunya..." -ForegroundColor Cyan
    Write-Host "AVIS: Pot trigar moltes hores. Els municipis ja descarregats es saltaran." -ForegroundColor Yellow
    docker compose exec api python -c @"
import sys, time
sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import settings

engine = create_engine(settings.database_url)
with Session(engine) as session:
    rows = session.execute(text('SELECT code_ine FROM core.municipality ORDER BY code_ine')).fetchall()
    codes = [r[0] for r in rows]

print(f'Total municipis: {len(codes)}')
import subprocess
for code in codes:
    result = subprocess.run(
        ['python', 'scripts/download_catastro.py', '--code', code],
        capture_output=False
    )
    time.sleep(0.5)
"@
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
elseif ($Action -eq "download-sentinel2")        { Do-DownloadSentinel2 }
elseif ($Action -eq "download-ndvi")             { Do-DownloadSentinel2 }
elseif ($Action -eq "download-catastro")         { Do-DownloadCatastro }
elseif ($Action -eq "download-catastro-all")     { Do-DownloadCatastroAll }
elseif ($Action -eq "calculate-ndvi")            { DC exec api python scripts/calculate_ndvi.py }
elseif ($Action -eq "aggregate-ndvi")            { DC exec api python scripts/aggregate_ndvi.py }
elseif ($Action -eq "classify-parcels")          { DC exec api python scripts/classify_parcels.py }
elseif ($Action -eq "pipeline") {
    Do-DownloadSentinel2
    DC exec api python scripts/calculate_ndvi.py
    DC exec api python scripts/aggregate_ndvi.py
    DC exec api python scripts/classify_parcels.py
}
else {
    Write-Host "Accions disponibles:" -ForegroundColor Cyan
    Write-Host "  setup, up, down, logs, build, restart"
    Write-Host "  migrate, migrate-down, shell-db, shell-api"
    Write-Host "  import-municipalities, import-parcels, import-sigpac"
    Write-Host ""
    Write-Host "  download-sentinel2  [-Start YYYY-MM-DD] [-End YYYY-MM-DD] [-MaxCloud 20]"
    Write-Host "  download-catastro   [-Name 'Vic,Manresa'] o [-Code '08001,08006']"
    Write-Host "  download-catastro-all  (tots els municipis de Catalunya)"
    Write-Host "  calculate-ndvi, aggregate-ndvi, classify-parcels"
    Write-Host "  pipeline  (sentinel2 + ndvi + classificacio)"
}
