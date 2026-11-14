# Pipeline NDVI amb GitHub Actions

Substitueix l'orquestrador de la Raspberry Pi ([raspberry-pi-setup.md](raspberry-pi-setup.md)).

```
GitHub Actions (cada dia 05:00 UTC)               PC (Docker)
──────────────────────────────────                ─────────────────────────────
release "parcels"  ── parcels.fgb ──┐
                                    ▼
Earth Search (COG Sentinel-2) ──► gha_ndvi_pipeline.py
                                    │
                                    ▼
release "ndvi-data": ndvi_YYYY-MM-DD.csv.gz ──►  import_ndvi_results.py
                     manifest.json                 → analytics.parcel_ndvi (upsert)
                                                   → analytics.ndvi_import (registre)
                                                   → classify_parcels.py
```

## Peces

| Fitxer | On s'executa | Què fa |
|---|---|---|
| `.github/workflows/ndvi.yml` | GitHub Actions | Cron diari + execució manual |
| `scripts/gha_ndvi_pipeline.py` | GitHub Actions | Cerca imatges, calcula NDVI, puja resultats |
| `scripts/import_ndvi_results.py` | PC (contenidor `api`) | Importa dates noves/reprocessades i reclassifica |
| `.\setup.ps1 publish-parcels` | PC | Exporta `core.parcel` i la puja a la release `parcels` |
| `.\setup.ps1 import-ndvi` | PC | Executa l'importador (també s'executa amb `.\setup.ps1 up`) |

## Càlcul

- **Font**: col·lecció `sentinel-2-c1-l2a` d'[Earth Search](https://earth-search.aws.element84.com/v1) (AWS, pública, sense credencials). Es llegeixen només les bandes B04, B08 i SCL i només la finestra que cobreix les parcel·les, sense descarregar el producte sencer.
- **Reflectància**: s'aplica `scale`/`offset` de les metadades STAC (`DN × 0.0001 − 0.1`).
- **NDVI píxel a píxel**, després agregat per parcel·la (mitjana, mín, màx, desviació).
- **Màscara de núvols** amb SCL: només compten les classes 4 (vegetació), 5 (sòl nu), 6 (aigua) i 7 (no classificat). Si menys del 50 % dels píxels de la parcel·la són clars, l'observació es descarta. `cloud_cover_pct` = % de píxels de la parcel·la emmascarats.
- Si una parcel·la cau a dos tiles el mateix dia, es queda l'observació amb més píxels clars.
- Filtre previ per tile: `eo:cloud_cover < 30 %` (configurable).

> Els valors són més alts que els del pipeline antic (Pi), que no corregia l'offset −1000 de les bandes ni emmascarava núvols. Les dates antigues dins la finestra de 365 dies se sobreescriuen automàticament quan el workflow les reprocessa.

## Ritme

- Cada execució processa fins a `MAX_DATES` (40) dates (~1 min per data), **de la més recent a la més antiga**, dins dels últims 365 dies.
- Cada data es puja a la release just en acabar-la: un timeout no fa perdre la feina feta.
- Les dates amb menys de 2 dies d'antiguitat s'esperen (el catàleg a vegades publica els tiles d'una passada amb retard).

## Operativa

```powershell
# Primer cop, o després de reimportar el Catastro
.\setup.ps1 publish-parcels

# Importar resultats (també s'executa automàticament amb `up`)
.\setup.ps1 import-ndvi

# Llançar el workflow manualment
gh workflow run ndvi.yml -f max_dates=10
gh workflow run ndvi.yml -f dates="2026-10-21 2026-10-28"   # reprocessar dates concretes
gh run watch
```

## Límits a tenir en compte

- El repositori és **públic**: les geometries i els resultats NDVI de les releases són descarregables per qualsevol. Si es fa privat: 2.000 min/mes gratuïts d'Actions i cal definir `GITHUB_TOKEN` al `.env` perquè l'importador pugui baixar els fitxers.
- GitHub desactiva els workflows programats d'un repo públic després de 60 dies sense activitat al repositori; si passa, reactivar-lo des de la pestanya *Actions*.
