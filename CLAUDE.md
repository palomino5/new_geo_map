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
| Processament GIS | GDAL · rasterio · numpy · rasterstats · geopandas |
| Frontend | React 18 · Vite · TypeScript · MapLibre GL JS |
| Infraestructura | Docker · docker-compose · Redis · Synology NAS |
| Dades | Catastro (SHP/GML) · ICGC · SIGPAC (FEGA/DARP) · Sentinel-2 (Copernicus) |

---

## Arquitectura del projecte

```
new_geo_map/
├── docker-compose.yml
├── .env.example
├── Makefile
├── CLAUDE.md
├── docs/
│   ├── data-sources.md
│   ├── classificacio-v1.md
│   ├── pipeline-ndvi.md
│   └── arquitectura-frontend.md
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── core/
│   ├── alembic/
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Map.tsx
│   │   │   └── FilterPanel.tsx
│   │   └── App.tsx
│   └── vite.config.ts
├── data/
│   ├── sentinel2/          # imatges per data: YYYY-MM-DD/
│   └── imports/            # shapefiles i GML del Catastro
├── scripts/
│   ├── import_municipalities.py
│   ├── import_parcels.py
│   ├── import_sigpac.py
│   ├── download_sentinel2.py
│   ├── calculate_ndvi.py
│   ├── aggregate_ndvi.py
│   └── classify_parcels.py
└── notebooks/
    └── classificacio-exploracio.ipynb
```

---

## Model de dades PostGIS

### Schemas
- `core` — dades mestres (municipis, parcel·les)
- `raw` — dades importades sense processar (SIGPAC)
- `analytics` — resultats NDVI i classificació

### Taules principals

```sql
core.municipality       -- 947 municipis de Catalunya, geom MULTIPOLYGON SRID 4326
core.parcel             -- parcel·les rústiques, ref_catastral (20 chars), geom POLYGON SRID 4326
raw.sigpac              -- usos agrícoles SIGPAC
raw.sigpac_parcel_match -- creuament SIGPAC ↔ parcel·les
analytics.parcel_ndvi   -- històric NDVI per parcel·la i data (ndvi_mean, min, max, std, cloud_cover_pct), UNIQUE (parcel_id, date)
analytics.ndvi_import   -- registre de dates importades des de GitHub Releases (processed_at)
analytics.parcel_status -- classificació per parcel·la: activa | abandonada | desconeguda + confidence (0.0–1.0)
```

### Vista clau
```sql
analytics.parcel_status_latest  -- estat més recent per parcel·la
```

---

## API REST (FastAPI)

| Endpoint | Descripció |
|---|---|
| `GET /health` | Health check |
| `GET /parcels` | GeoJSON FeatureCollection amb filtres: `municipality_id`, `bbox`, `limit` |
| `GET /parcels/status` | Estat classificació per parcel·la amb filtres: `status`, `municipality_id`, `fecha` |
| `GET /municipalities` | Llista municipis (per al combobox del frontend) |

- Port: `8000`
- CORS: `http://localhost:5173`
- Docs: `/docs` (Swagger), `/redoc`

---

## Frontend (React + MapLibre GL)

- Mapa centrat a Catalunya: `center [1.7, 41.8]`, `zoom 7`
- Capa GeoJSON de parcel·les carregada dinàmicament per bounding box visible (event `moveend`)
- **Zoom mínim per parcel·les**: `MIN_ZOOM_PARCELS = 11`. Per sota d'aquest zoom, la capa de parcel·les s'amaga i es mostra el missatge "Fes zoom per veure les parcel·les". Per sobre, es carreguen automàticament les parcel·les del bbox visible sense necessitat de seleccionar municipi.
- Colors per estat:
  - Activa → `#3B6D11` (verd), opacitat proporcional a `confidence`
  - Abandonada → `#D85A30` (coral), opacitat proporcional a `confidence`
  - Desconeguda → `#888780` (gris)
- Panel lateral de filtres (280px, col·lapsable): municipi, superfície (ha), estat
- Variable d'entorn: `VITE_API_URL=http://localhost:8000`

---

## Classificació d'abandonament (v1.0)

Regles heurístiques basades en NDVI i SIGPAC:

- **Activa**: `ndvi_mean > 0.3` en almenys 2 de les últimes 4 imatges
- **Abandonada**: `ndvi_mean < 0.15` de forma consistent durant els últims 12 mesos
- **Desconeguda**: dades insuficients o ús SIGPAC no agrícola → `confidence` reduït

Cada registre a `parcel_status` inclou `algoritmo_version` ('v1.0') i `confidence` (0.0–1.0).

---

## Roadmap MVP

### MVP v0.1 (prioritat alta)
- [x] Definir issues i tasques al GitHub Project
- [ ] Entorn Docker (docker-compose + .env + persistència)
- [ ] Esquema PostGIS (extensions + schemas + taules)
- [ ] Backend FastAPI (estructura + connexió DB + endpoints)
- [ ] Ingesta dades Catalunya (municipis + parcel·les + SIGPAC)
- [ ] Frontend mapa interactiu (React + MapLibre + filtres)

### MVP v0.2
- [ ] Processament NDVI (descàrrega Sentinel-2 + càlcul raster + agregació per parcel·la)
- [ ] Classificació abandonament (regles v1 + generació parcel_status)
- [ ] Optimització rendiment geometries (vector tiles o simplificació)

### Implementat (fora roadmap inicial)
- [x] Landing page (hero, stats, casos d'ús, preus)
- [x] Autenticació JWT (register/login/logout, pla free/starter/professional/enterprise)
- [x] Freemium: límit 10 consultes/dia pla free, pàgina `/compte` amb barra d'ús
- [x] Panell detall parcel·la (gràfic NDVI SVG, estat, confiança) — requereix login
- [x] Pàgina pública `/parcela/:ref_catastral` (preview 3 punts NDVI, CTA upgrade)
- [x] Càrrega automàtica de parcel·les per bbox al fer zoom ≥ 11 (sense selecció manual de municipi)
- [x] ~~Pipeline autònom Raspberry Pi 3B~~ (obsolet, substituït pel següent)
- [x] Pipeline NDVI a GitHub Actions (`.github/workflows/ndvi.yml`): COG Sentinel-2 d'Earth Search → NDVI amb màscara SCL → release `ndvi-data` → `.\setup.ps1 import-ndvi` al PC. Vegeu `docs/pipeline-ndvi.md`

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

## Convencions de codi

- **Python**: tipus estrictes, `pydantic` per a tots els schemas, funcions pures per a les regles de classificació
- **SQL**: scripts idempotents (`INSERT ... ON CONFLICT DO UPDATE`), sempre especificar SRID explícitament
- **TypeScript**: tipus estrictes, no `any`
- **Git**: branques per epic (`epic/docker`, `epic/postgis`, `epic/api`, `epic/frontend`)
- **Scripts**: executables via `Makefile` (`make import-parcels`, `make download-ndvi`, etc.)

---

## Fonts de dades

| Font | URL | Format |
|---|---|---|
| Municipis Catalunya | https://www.icgc.cat | SHP / GeoJSON |
| Parcel·les Catastro | https://www.sedecatastro.gob.es | SHP / GML |
| SIGPAC | https://www.fega.gob.es / https://agricultura.gencat.cat | SHP |
| Sentinel-2 | https://dataspace.copernicus.eu | GeoTIFF (B04, B08) |

---

## Variables d'entorn (.env.example)

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

---

## Repositori GitHub

- **Repo**: https://github.com/palomino5/new_geo_map
- **Project board**: https://github.com/users/palomino5/projects/2
- **Issues**: 26 issues creades amb criteris d'acceptació detallats, organitzades en 6 epics i 2 milestones (MVP v0.1 i MVP v0.2)
