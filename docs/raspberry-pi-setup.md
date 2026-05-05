# Configuració Raspberry Pi 3B — Pipeline autònom

## Requisits

- Raspberry Pi 3B amb Raspberry Pi OS (64-bit recomanat)
- Python 3.11+
- Accés a la base de dades PostgreSQL (mateixa xarxa o exposada)
- Compte Copernicus CDSE actiu

---

## 1. Instal·lació de dependències del sistema

```bash
sudo apt update && sudo apt install -y \
  python3-pip python3-venv \
  gdal-bin libgdal-dev \
  libgeos-dev libproj-dev \
  git
```

## 2. Clonar el projecte

```bash
git clone https://github.com/palomino5/new_geo_map.git /home/pi/geo_map
cd /home/pi/geo_map
```

## 3. Entorn virtual i dependències

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install \
  sqlalchemy psycopg2-binary geoalchemy2 alembic \
  rasterio rasterstats numpy shapely pyproj \
  httpx python-dotenv
```

> **Nota Pi 3B:** `rasterio` pot trigar 10-15 minuts en compilar. És normal.

## 4. Configuració (.env)

Crea `/home/pi/geo_map/.env`:

```env
DATABASE_URL=postgresql://geomap:changeme@192.168.1.X:5432/geomap
COPERNICUS_USER=el_teu_usuari@email.com
COPERNICUS_PASS=la_teva_contrasenya
SENTINEL_DATA_DIR=/home/pi/geo_map/data/sentinel2
LOOP_INTERVAL_H=24
LOOKBACK_DAYS=30
MAX_CLOUD=20
LOG_FILE=/home/pi/geo_map/orchestrator.log
```

Substitueix `192.168.1.X` per la IP del teu ordinador amb la base de dades.

> **Important:** La base de dades ha d'acceptar connexions externes.  
> Al `docker-compose.yml` del teu PC assegura't que el port 5432 estigui exposat:
> ```yaml
> db:
>   ports:
>     - "5432:5432"
> ```
> I a PostgreSQL: edita `pg_hba.conf` per permetre la IP de la Pi,  
> o afegeix `POSTGRES_HOST_AUTH_METHOD=md5` al docker-compose.

## 5. Test manual

```bash
cd /home/pi/geo_map
source venv/bin/activate

# Comprova estat actual
python scripts/orchestrator.py --status

# Executa un cicle complet
python scripts/orchestrator.py --once
```

## 6. Servei systemd (arrenca automàticament al boot)

Crea `/etc/systemd/system/geomap.service`:

```ini
[Unit]
Description=GeoMap Pipeline Orquestrador
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/geo_map
ExecStart=/home/pi/geo_map/venv/bin/python scripts/orchestrator.py
Restart=on-failure
RestartSec=60
EnvironmentFile=/home/pi/geo_map/.env
StandardOutput=append:/home/pi/geo_map/orchestrator.log
StandardError=append:/home/pi/geo_map/orchestrator.log

[Install]
WantedBy=multi-user.target
```

Activa el servei:

```bash
sudo systemctl daemon-reload
sudo systemctl enable geomap
sudo systemctl start geomap
```

## 7. Monitorització

```bash
# Estat del servei
sudo systemctl status geomap

# Log en temps real
tail -f /home/pi/geo_map/orchestrator.log

# Estat del pipeline
cd /home/pi/geo_map && source venv/bin/activate
python scripts/orchestrator.py --status
```

## Consideracions Pi 3B (1GB RAM)

- El `BATCH_SIZE` de `calculate_ndvi.py` ja és 5.000 — si la Pi es queda sense memòria, redueix-lo a 2.000 editant la variable al principi del script.
- Les imatges Sentinel-2 pesen ~100-500 MB cada una. Assegura't de tenir una targeta SD d'almenys 64 GB o un disc extern.
- La Pi 3B és lenta processant rasters grans. Un tile pot trigar 10-30 minuts.
