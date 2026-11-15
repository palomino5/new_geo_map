# Desplegament a la Synology DS224+

Executa l'aplicació completa (PostGIS + API + web) a la NAS amb `docker-compose.prod.yml`.
Les dades NDVI arriben de GitHub Actions (vegeu [pipeline-ndvi.md](pipeline-ndvi.md)) i
s'importen amb una tasca programada.

```
Internet ──► (Cloudflare Tunnel  o  proxy invers DSM :443) ──► web :8080 (nginx)
                                                                 ├── /      → frontend estàtic
                                                                 └── /api/  → api:8000 ──► db, redis
```

## Requisits

- DSM 7.2+ amb **Container Manager** instal·lat (Centre de paquets).
- **RAM**: funciona amb els 2 GB de sèrie amb els valors per defecte de `.env.prod`; amb 6 GB, puja els límits (vegeu els comentaris a `.env.prod.example`).
- Accés SSH a la NAS: *Panell de control → Terminal i SNMP → Habilita SSH*.
- ~5 GB lliures al volum (BD + imatges Docker).

## 1. Copiar el projecte a la NAS

```bash
ssh <usuari>@<ip-nas>
sudo -i
mkdir -p /volume1/docker && cd /volume1/docker
git clone https://github.com/palomino5/new_geo_map.git     # o copia la carpeta amb File Station
cd new_geo_map
cp .env.prod.example .env.prod
vi .env.prod          # canvia POSTGRES_PASSWORD i API_SECRET_KEY
```

> Si `git` no hi és: instal·la el paquet *Git Server* o copia la carpeta del PC amb File Station
> (sense `node_modules`, `data/` ni `backend/data/`).

## 2. Arrencar

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

La primera construcció triga (compila dependències GIS): 20–40 min a la DS224+.

## 3. Migrar la base de dades del PC

Al PC:

```powershell
.\setup.ps1 dump-db      # genera data/exports/geomap.dump (~200 MB)
```

Copia `geomap.dump` a `/volume1/docker/new_geo_map/data/exports/` (File Station o `scp`) i a la NAS:

```bash
cd /volume1/docker/new_geo_map
docker compose -f docker-compose.prod.yml --env-file .env.prod exec db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /exports/geomap.dump'
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api alembic upgrade head
```

Comprova: `http://<ip-nas>:8080` ha de mostrar el mapa amb parcel·les.

## 4. Importació NDVI diària

*Panell de control → Programador de tasques → Crea → Tasca programada → Script definit per l'usuari*

- Usuari: `root`
- Programació: diària, 09:00 (el workflow de GitHub s'executa a les 05:00 UTC)
- Script:

```bash
cd /volume1/docker/new_geo_map && \
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T api \
  python scripts/import_ndvi_results.py >> /volume1/docker/new_geo_map/import-ndvi.log 2>&1
```

Marca *Envia els detalls d'execució per correu* si vols avís en cas d'error.

## 5. Accés des d'internet

### Opció A — Cloudflare Tunnel (cal domini propi a Cloudflare, sense obrir ports)

1. Compra o trasllada un domini a Cloudflare (~10–15 €/any).
2. *Cloudflare Zero Trust → Networks → Tunnels → Create tunnel* (tipus *Cloudflared*). Copia el token.
3. *Public Hostname*: `geomap.<domini>` → servei `http://web:80`.
4. A `.env.prod`: `CLOUDFLARE_TUNNEL_TOKEN=<token>` i:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile tunnel up -d
```

### Opció B — DDNS de Synology (gratis, cal obrir el port 443)

1. *Panell de control → Accés extern → DDNS → Afegeix* → proveïdor Synology → `<nom>.synology.me`.
2. *Panell de control → Seguretat → Certificat → Afegeix* → Let's Encrypt per a `<nom>.synology.me`.
3. *Panell de control → Portal d'inici de sessió → Avançat → Proxy invers → Crea*:
   origen `HTTPS <nom>.synology.me:443` → destí `HTTP localhost:8080`.
4. Al router: redirigeix el port TCP 443 cap a la IP de la NAS.

## Actualitzar

```bash
cd /volume1/docker/new_geo_map && git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api alembic upgrade head
```

## Seguretat

- Postgres i Redis **no** publiquen ports; només `web` (8080).
- `.env.prod` no es puja mai al repositori (és al `.gitignore`).
- Fes còpies de la BD periòdicament (Hyper Backup del volum Docker, o `pg_dump` programat).
