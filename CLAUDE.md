# CLAUDE.md — new_geo_map

## Descripció del projecte

Aplicació web per conèixer l'estat dels camps de Catalunya: si estan cultivats o abandonats.
Les dades s'obtenen creuant **referències catastrals rústiques** amb **imatges de cartografia satelital (Sentinel-2)** per calcular l'índex NDVI per parcel·la.

---

## Stack tecnològic

| Capa | Tecnologia |
|---|---|
| Base de dades | PostgreSQL 15 + PostGIS |
| Backend | Python · FastAPI · SQLAlchemy · GeoAlchemy2 · Alembic |
| Processament GIS | GDAL · rasterio · numpy · geopandas |
| Frontend | React 18 · Vite · TypeScript · MapLibre GL JS |
| Infraestructura | Docker · docker-compose · Redis · nginx · GitHub Actions · Synology NAS |
| Dades | Catastro INSPIRE (ATOM) · ICGC · SIGPAC (FEGA/DARP) · Sentinel-2 L2A (Earth Search, AWS) |

---

## On s'executa cada cosa

```
GitHub Actions (cron diari 05:00 UTC, pot arribar amb hores de retard)
  .github/workflows/ndvi.yml → scripts/gha_ndvi_pipeline.py
  llegeix release "parcels" (parcels.fgb) + COG Sentinel-2 → publica release "ndvi-data"
        │
        ▼
Synology DS224+ (producció) — 192.168.1.201, /volume1/docker/new_geo_map
  docker-compose.prod.yml: db · redis · api · web (nginx :8080) · ndvi-import
  ndvi-import comprova la release cada 6 h, importa dates noves i reclassifica
        ▲
PC Windows (desenvolupament) — docker-compose.yml + setup.ps1
  importació de parcel·les, publicació de parcels.fgb, construcció d'imatges per a la NAS
```

- La **Raspberry Pi** ja no s'utilitza (`docs/raspberry-pi-setup.md` és obsolet).
- Detalls: `docs/pipeline-ndvi.md` (NDVI) i `docs/deploy-nas.md` (NAS).

---

## Arquitectura del projecte

```
new_geo_map/
├── docker-compose.yml          # desenvolupament (PC)
├── docker-compose.prod.yml     # producció (NAS)
├── .env.example / .env.prod.example
├── setup.ps1                   # equivalent del Makefile a Windows
├── .github/workflows/ndvi.yml  # pipeline NDVI
├── docs/
│   ├── pipeline-ndvi.md
│   ├── deploy-nas.md
│   └── raspberry-pi-setup.md   # obsolet
├── backend/
│   ├── app/ (api, models, schemas, core)
│   ├── alembic/versions/       # migracions 0001–0006
│   └── main.py
├── frontend/
│   ├── src/
│   ├── Dockerfile              # producció: build + nginx (proxy /api → api:8000)
│   ├── Dockerfile.dev
│   └── nginx.conf
└── scripts/
    ├── import_municipalities.py
    ├── import_catastro_atom.py   # parcel·les rústiques de tot Catalunya (ATOM INSPIRE)
    ├── import_sigpac.py
    ├── gha_ndvi_pipeline.py      # s'executa a GitHub Actions
    ├── import_ndvi_results.py    # importa la release ndvi-data a la BD
    ├── classify_parcels.py
    └── (llegat) download_catastro.py, download_sentinel2.py, calculate_ndvi.py, orchestrator.py
```

---

## Model de dades PostGIS

### Schemas
- `core` — dades mestres (municipis, parcel·les, usuaris)
- `raw` — dades importades sense processar (SIGPAC)
- `analytics` — resultats NDVI i classificació

### Taules principals

```sql
core.municipality       -- 948 municipis de Catalunya, geom MULTIPOLYGON SRID 4326
core.parcel             -- NOMÉS parcel·les rústiques: ref_catastral de 14 caràcters PPMMM A PPP PPPPP
                        -- (regex ^[0-9]{5}[A-Z][0-9]{8}$), geom MULTIPOLYGON SRID 4326, UNIQUE ref_catastral
raw.sigpac              -- usos agrícoles SIGPAC
raw.sigpac_parcel_match -- creuament SIGPAC ↔ parcel·les
analytics.parcel_ndvi   -- històric NDVI per parcel·la i data (ndvi_mean, min, max, std, cloud_cover_pct), UNIQUE (parcel_id, date)
analytics.ndvi_import   -- registre de dates importades des de GitHub Releases (processed_at)
analytics.parcel_status -- classificació per parcel·la: activa | abandonada | desconeguda + confidence (0.0–1.0), UNIQUE parcel_id
```

- Els `id` de `core.parcel` són la clau que fa servir el pipeline NDVI (via `parcels.fgb`). La BD de producció i la de desenvolupament han de compartir els mateixos ids: les parcel·les s'importen al PC i es traslladen a la NAS amb `pg_dump`/`pg_restore`.

---

## API REST (FastAPI)

| Endpoint | Descripció |
|---|---|
| `GET /health` | Health check |
| `GET /parcels` | GeoJSON FeatureCollection amb filtres: `municipality_id`, `bbox`, `limit` |
| `GET /parcels/status` | Estat classificació per parcel·la amb filtres: `status`, `municipality_id`, `fecha` |
| `GET /parcels/{ref_catastral}` | Detall de parcel·la (requereix login) |
| `GET /municipalities` | Llista municipis (per al combobox del frontend) |
| `/auth/*` | Registre, login, usuari actual, ús diari |

- Desenvolupament: port `8000`, CORS `http://localhost:5173`
- Producció: darrere nginx a `/api/` (mateix origen, sense CORS). `CORS_ORIGINS` configurable per entorn.
- Docs: `/docs` (Swagger), `/redoc`

---

## Frontend (React + MapLibre GL)

- Mapa centrat a Catalunya: `center [1.7, 41.8]`, `zoom 7`
- Capa GeoJSON de parcel·les carregada dinàmicament per bounding box visible (event `moveend`)
- **Zoom mínim per parcel·les**: `MIN_ZOOM_PARCELS = 11`. Per sota, la capa s'amaga i es mostra "Fes zoom per veure les parcel·les".
- Colors per estat:
  - Activa → `#3B6D11` (verd), opacitat proporcional a `confidence`
  - Abandonada → `#D85A30` (coral), opacitat proporcional a `confidence`
  - Desconeguda → `#888780` (gris)
- Panel lateral de filtres (280px, col·lapsable): municipi, superfície (ha), estat
- `VITE_API_URL`: `http://localhost:8000` en desenvolupament, `/api` en producció. Les URLs es construeixen amb `new URL(path, window.location.origin)` perquè funcionin amb base relativa.
- El build de producció executa `tsc`: cap variable sense ús ni error de tipus.

---

## Càlcul NDVI

- Font: col·lecció `sentinel-2-c1-l2a` d'Earth Search (COG públics, sense credencials). Només bandes B04, B08 i SCL, i només la finestra amb parcel·les.
- Reflectància = `DN × 0.0001 − 0.1` (offset de les metadades STAC). NDVI píxel a píxel, agregat per parcel·la.
- Màscara de núvols SCL (classes 4, 5, 6, 7 vàlides); observació descartada si < 50 % de píxels clars.
- Cada data publicada es marca amb la versió de `parcels.fgb`: si es republiquen les parcel·les, totes les dates es reprocessen automàticament.
- L'importador substitueix completament cada data a `parcel_ndvi`.
- Les dades del pipeline antic (Raspberry, abans de 2026-11) estaven esbiaixades a la baixa (sense offset ni màscara de núvols).

---

## Classificació d'abandonament (v2.0)

`scripts/classify_parcels.py`, funció pura `classify_parcel()`, execució per lots (`CLASSIFY_BATCH`, 5000 a la NAS):

- **Activa**: NDVI > 0.3 en ≥ 2 de les últimes 4 imatges i variabilitat (std ≥ 0.05) per distingir cultiu de bosc
- **Abandonada**: NDVI < 0.15 en totes les imatges dels últims 12 mesos (≥ 3 observacions)
- **Desconeguda**: bosc/matollar estable (mitjana ≥ 0.35 i std ≤ 0.06), dades insuficients o ús SIGPAC no agrícola

Cada registre a `parcel_status` inclou `algoritmo_version` ('v2.0') i `confidence` (0.0–1.0).
Els llindars es van fixar amb l'NDVI antic (esbiaixat a la baixa); de moment es mantenen i es validen visualment.

---

## Roadmap

### MVP v0.1 / v0.2 — fet
- [x] Issues i tasques al GitHub Project
- [x] Entorn Docker (desenvolupament i producció)
- [x] Esquema PostGIS (migracions Alembic 0001–0006)
- [x] Backend FastAPI
- [x] Ingesta: municipis, parcel·les rústiques de tot Catalunya (ATOM), SIGPAC
- [x] Frontend mapa interactiu
- [x] Processament NDVI (GitHub Actions)
- [x] Classificació d'abandonament v2.0
- [ ] Optimització rendiment geometries (vector tiles o simplificació)

### Implementat (fora roadmap inicial)
- [x] Landing page (hero, stats, casos d'ús, preus)
- [x] Autenticació JWT (register/login/logout, pla free/starter/professional/enterprise)
- [x] Freemium: límit 10 consultes/dia pla free, pàgina `/compte` amb barra d'ús
- [x] Panell detall parcel·la (gràfic NDVI SVG, estat, confiança) — requereix login
- [x] Pàgina pública `/parcela/:ref_catastral` (preview 3 punts NDVI, CTA upgrade)
- [x] Càrrega automàtica de parcel·les per bbox al fer zoom ≥ 11
- [x] Pipeline NDVI a GitHub Actions + importació automàtica cada 6 h
- [x] Desplegament a Synology DS224+ (`docker-compose.prod.yml`)
- [ ] Accés públic per DDNS de Synology + proxy invers DSM (pendent de configurar a DSM i al router)

### MVP v0.3 — Accessibilitat viària (pendent)
- [ ] Descarregar xarxa viària OSM de Catalunya (osmnx o fitxer .osm.pbf)
- [ ] Script `calculate_accessibility.py`: distància mínima parcel·la → via + classificació
- [ ] Nova taula `analytics.parcel_accessibility`
- [ ] Nou camp `accessibility` a `ParcelDetail` i `ParcelPublic`
- [ ] Filtre d'accessibilitat al panell lateral del mapa
- [ ] Visualització al panell de detall i pàgina pública

#### Classificació d'accessibilitat viària (v1.0)
Basada en distància a la via més propera i el seu tipus OSM:

| Condició | Valor | Descripció |
|---|---|---|
| Distància > 500m a qualsevol via | `nula` | Parcel·la aillada |
| Via més propera és `track` / `path` | `baixa` | Camí agrícola o de terra |
| Via més propera és `unclassified` / `tertiary` | `mitjana` | Carretera local |
| Via més propera és `secondary` o millor | `bona` | Carretera principal |

Font de dades: OpenStreetMap via `osmnx` (Python). Actualització trimestral recomanada.

---

## Operativa habitual

```powershell
# PC (desenvolupament)
.\setup.ps1 up                 # arrenca i importa NDVI pendent
.\setup.ps1 import-ndvi        # importa resultats NDVI de GitHub
.\setup.ps1 publish-parcels    # exporta core.parcel i la puja a la release 'parcels'
.\setup.ps1 dump-db            # còpia de la BD per migrar a la NAS
docker compose exec api python scripts/import_catastro_atom.py all   # parcel·les de tot Catalunya

# GitHub
gh workflow run ndvi.yml -f max_dates=250
gh workflow run ndvi.yml -f dates="2024-02-10 2024-03-05"   # dates concretes, encara que siguin antigues
```

NAS: accés per SSH `carlos.feliu@192.168.1.201` (clau del PC, `sudo /usr/local/bin/docker` sense contrasenya). Procediments a `docs/deploy-nas.md`.

---

## Convencions de codi

- **Python**: tipus estrictes, `pydantic` per a tots els schemas, funcions pures per a les regles de classificació
- **SQL**: scripts idempotents (`INSERT ... ON CONFLICT DO UPDATE`), sempre especificar SRID explícitament
- **TypeScript**: tipus estrictes, no `any`
- **Git**: branques per epic (`epic/docker`, `epic/postgis`, `epic/api`, `epic/frontend`); missatges de commit en català
- **Scripts**: a Windows via `setup.ps1` (no hi ha `make`)
- **Windows / Docker**: escriure fitxers grans dins el contenidor (`/tmp`) i copiar-los amb `docker compose cp`; el volum compartit amb Windows és molt lent. No passar binaris per pipes de PowerShell.

---

## Fonts de dades

| Font | URL | Format |
|---|---|---|
| Municipis Catalunya | https://www.icgc.cat | SHP / GeoJSON |
| Parcel·les Catastro (ATOM INSPIRE) | https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels/{08,17,25,43}/ | ZIP amb GML per municipi |
| SIGPAC | https://www.fega.gob.es / https://agricultura.gencat.cat | SHP |
| Sentinel-2 L2A | https://earth-search.aws.element84.com/v1 (`sentinel-2-c1-l2a`) | COG (B04, B08, SCL) |

---

## Variables d'entorn

Desenvolupament (`.env`, a partir de `.env.example`):

```env
POSTGRES_USER=geomap
POSTGRES_PASSWORD=changeme
POSTGRES_DB=geomap
POSTGRES_HOST=db
POSTGRES_PORT=5432
REDIS_URL=redis://redis:6379/0
API_SECRET_KEY=changeme
FRONTEND_API_URL=http://localhost:8000
```

Producció (`.env.prod`, a partir de `.env.prod.example`, només a la NAS): a més, `WEB_PORT`, `CORS_ORIGINS`, límits de memòria (`PG_SHARED_BUFFERS`, `DB_MEM_LIMIT`, `API_MEM_LIMIT`, `IMPORT_MEM_LIMIT`), `CLASSIFY_BATCH`, `IMPORT_INTERVAL_H` i `CLOUDFLARE_TUNNEL_TOKEN` (opcional).

Importador NDVI: `GITHUB_REPO`, `NDVI_RELEASE`, `GITHUB_TOKEN` (només si el repo passa a privat).

---

## Repositori GitHub

- **Repo**: https://github.com/palomino5/new_geo_map (públic: les releases `parcels` i `ndvi-data` són descarregables per tothom)
- **Project board**: https://github.com/users/palomino5/projects/2
- **Issues**: 26 issues creades amb criteris d'acceptació detallats, organitzades en 6 epics i 2 milestones (MVP v0.1 i MVP v0.2)
