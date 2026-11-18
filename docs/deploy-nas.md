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

## 2. Imatges Docker

Amb 2 GB de RAM, compilar les dependències GIS a la NAS pot quedar-se sense memòria.
Es construeixen al PC i es copien (cal la clau SSH del PC autoritzada a la NAS i
`sudo` sense contrasenya per a `docker`, vegeu *Accés SSH* més avall):

```bash
# Al PC (Git Bash), des de l'arrel del projecte
docker compose -f docker-compose.prod.yml --env-file .env.prod.example build api web
docker save geomap-api:latest geomap-web:latest | gzip -1 | \
  ssh carlos.feliu@192.168.1.201 'gunzip | sudo /usr/local/bin/docker load'
```

Amb més RAM també es pot fer directament a la NAS: `... up -d --build`.

Arrencar (a la NAS):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

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

La fa el servei `ndvi-import` del mateix compose: cada `IMPORT_INTERVAL_H` hores (6 per defecte)
executa `import_ndvi_results.py`, que només importa i reclassifica si hi ha dates noves.
No es fa a hora fixa perquè els crons de GitHub poden arribar amb hores de retard.
No cal configurar res a DSM.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail 50 ndvi-import
# Forçar una importació ara:
docker compose -f docker-compose.prod.yml --env-file .env.prod exec ndvi-import python scripts/import_ndvi_results.py
```

## Accés SSH des del PC (per a manteniment)

```powershell
# Al PC: clau i autorització (demana la contrasenya de DSM)
ssh-keygen -t ed25519 -N '""' -f $HOME\.ssh\id_ed25519
type $HOME\.ssh\id_ed25519.pub | ssh carlos.feliu@192.168.1.201 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 755 ~ && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
# docker amb sudo sense contrasenya (només docker)
ssh -t carlos.feliu@192.168.1.201 "echo 'carlos.feliu ALL=(ALL) NOPASSWD: /usr/local/bin/docker' | sudo tee /etc/sudoers.d/geomap && sudo chmod 440 /etc/sudoers.d/geomap"
```

Requereix *Panell de control → Usuari i grup → Avançat → Habilita el servei d'inici d'usuari*.
Una actualització gran de DSM pot esborrar `/etc/sudoers.d/geomap`: torna-ho a executar.

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

Des del PC (Git Bash): copia els fitxers del repositori, reconstrueix i copia les imatges (pas 2) i:

```bash
git ls-files -z | grep -zv "^.claude/" | tar --null -T - -cf - | \
  ssh carlos.feliu@192.168.1.201 'tar -xf - -C /volume1/docker/new_geo_map'
ssh carlos.feliu@192.168.1.201 'cd /volume1/docker/new_geo_map && \
  sudo /usr/local/bin/docker compose -f docker-compose.prod.yml --env-file .env.prod up -d && \
  sudo /usr/local/bin/docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T api alembic upgrade head'
```

## Seguretat

- Postgres i Redis **no** publiquen ports; només `web` (8080).
- `.env.prod` no es puja mai al repositori (és al `.gitignore`).
- Fes còpies de la BD periòdicament (Hyper Backup del volum Docker, o `pg_dump` programat).
