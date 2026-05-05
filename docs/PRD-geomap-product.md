# GeoMap Agrícola — Product Requirements Document (PRD)
**Versió:** 1.0 · **Data:** Abril 2026 · **Autor:** Product Team  
**Estat:** Draft — pendent de revisió

---

## 1. Visió del Producte

> **"La primera plataforma que permet saber, en temps real i per qualsevol parcel·la agrícola de Catalunya, si un camp està cultivat o abandonat — i per quant de temps."**

Creiem que propietaris, inversors, asseguradores i administracions necessiten dades fiables sobre l'estat real dels camps agrícoles. Avui aquesta informació no existeix de forma accessible, actualitzada ni estructurada. Nosaltres la fem possible creuant dades catastrals amb imatges de satèl·lit Sentinel-2.

---

## 2. El Problema

### Qui pateix el problema?

| Actor | Problema actual |
|---|---|
| **Propietari agrícola** | No sap si les seves finques arrendades s'estan cultivant realment |
| **Comprador de terra** | No pot verificar l'historial d'ús d'una parcel·la abans de comprar |
| **Asseguradora agrícola** | Ha d'enviar inspectors físics per verificar l'estat dels camps assegurats |
| **Notari / gestor** | No té dades objectives sobre l'estat d'ús en transmissions patrimonials |
| **Administració pública** | Manca de dades per planificar polítiques d'abandó i reactivació agrícola |
| **Inversor en terra** | No pot avaluar el potencial productiu d'una finca a distància |

### Magnitud del problema
- **~1,2 milions** de parcel·les rústiques a Catalunya
- **~30% estimat** en situació d'abandó o ús incert (font: DARP)
- Inspeccions manuals costen entre **50–200€/parcel·la**
- Cap plataforma pública actualitza les dades més d'un cop cada **5 anys**

---

## 3. La Solució

```
┌─────────────────────────────────────────────────────────────┐
│                     GEOMAP AGRÍCOLA                         │
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐  │
│  │ Catastro │    │Sentinel-2│    │   Motor NDVI +        │  │
│  │  INSPIRE │───▶│ imatges  │───▶│   Classificació      │  │
│  │ (parceles│    │ (5 dies) │    │   activa/abandonada   │  │
│  └──────────┘    └──────────┘    └──────────┬───────────┘  │
│                                             │               │
│                                             ▼               │
│                              ┌─────────────────────────┐   │
│                              │  API REST + Mapa web     │   │
│                              │  (actualització mensual) │   │
│                              └─────────────┬───────────┘   │
│                                            │                │
│              ┌─────────────────────────────┴──────────┐    │
│              │                                         │    │
│         ┌────▼────┐    ┌──────────┐    ┌───────────┐  │    │
│         │Propiet. │    │Assegurad.│    │Administr. │  │    │
│         │Inversors│    │Notaries  │    │Investigad.│  │    │
│         └─────────┘    └──────────┘    └───────────┘  │    │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Arquitectura Web del Producte

### 4.1 Estructura de pàgines

```
geomap.cat/
│
├── / (Landing page pública)
│   ├── Hero: mapa demo interactiu de Catalunya
│   ├── Cas d'ús per perfil (Propietari / Empresa / Administració)
│   ├── Preus
│   └── CTA: "Prova gratuïta 14 dies"
│
├── /mapa (Aplicació principal — freemium)
│   ├── Mapa MapLibre amb parcel·les
│   ├── Filtre per municipi / comarca / província
│   ├── Filtre per estat (activa / abandonada)
│   ├── Historial NDVI per parcel·la (click)
│   └── [PREMIUM] Export CSV/GeoJSON + alertes
│
├── /parcela/:ref_catastral (Fitxa de parcel·la — pública bàsica)
│   ├── Mapa centrat a la parcel·la
│   ├── Estat actual + data d'actualització
│   ├── [PREMIUM] Historial complet 3 anys
│   └── [PREMIUM] PDF informe
│
├── /dashboard (Àrea privada — usuaris registrats)
│   ├── Les meves parcel·les (afegides manualment o per codi)
│   ├── Alertes configurades
│   ├── Informes generats
│   └── Ús de l'API
│
├── /api-docs (Documentació API pública)
│
└── /auth (Login / Registre / Plans)
```

### 4.2 Components clau del frontend

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR: Logo | Mapa | Preus | Login/Avatar                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌──────────────────────────────────────┐  │
│  │ FILTRE PANEL│  │                                      │  │
│  │─────────────│  │          MAPA INTERACTIU             │  │
│  │ Comarca ▼   │  │         (MapLibre GL JS)             │  │
│  │ Municipi ▼  │  │                                      │  │
│  │─────────────│  │  ██ Activa    ██ Abandonada          │  │
│  │ Estat:      │  │  ██ Descon.                          │  │
│  │ ☑ Activa    │  │                                      │  │
│  │ ☑ Abandonada│  │                                      │  │
│  │ ☑ Desconeg. │  │                                      │  │
│  │─────────────│  └──────────────────────────────────────┘  │
│  │ Superfície  │  ┌──────────────────────────────────────┐  │
│  │ [0] a [50]ha│  │  PANEL PARCEL·LA (click al mapa)     │  │
│  │─────────────│  │  Ref: 08001A00100001                  │  │
│  │[PREMIUM]    │  │  Estat: 🟢 Activa (conf. 87%)        │  │
│  │ Export CSV  │  │  Última imatge: 15 mar 2024          │  │
│  │ Alertes     │  │  [PREMIUM] Veure historial complet   │  │
│  └─────────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Model de Negoci

### 5.1 Segments de clients i disposició a pagar

```
                     DISPOSICIÓ A PAGAR
                         Alta ▲
                          │
      Asseguradores ●──── │ ──── B2B API
      Gestories/Notaries●─┤      (500-2000€/mes)
                          │
      Inversors terra ●───┤──── Professional
                          │      (49€/mes)
      Propietaris >5 fin●─┤
                          │
      Propietaris 1-2 fin─┤──── Starter / Freemium
                          │      (0-9€/mes)
                          │
          Baixa ◄──────── │ ────────────────► Alta
                       Volum d'usuaris
```

### 5.2 Plans i preus

| | **Free** | **Starter** | **Professional** | **API / Enterprise** |
|---|---|---|---|---|
| **Preu** | 0€ | 9€/mes | 49€/mes | Des de 299€/mes |
| Mapa interactiu | ✅ | ✅ | ✅ | Via API |
| Veure estat parcel·les | Limitat (10/dia) | ✅ Il·limitat | ✅ Il·limitat | ✅ Il·limitat |
| Historial NDVI | Últim mes | 1 any | 3 anys | 3 anys |
| Export CSV/GeoJSON | ❌ | 500 parc/mes | Il·limitat | Il·limitat |
| Informes PDF | ❌ | 5/mes | Il·limitat | Il·limitat |
| Alertes canvi d'estat | ❌ | 10 parcel·les | Il·limitat | Il·limitat |
| Accés API REST | ❌ | ❌ | 10k req/mes | Il·limitat + SLA |
| Integració webhook | ❌ | ❌ | ❌ | ✅ |
| Suport | Comunitat | Email | Prioritari | Compte dedicat |

### 5.3 Projeccions conservadores (any 1)

```
MES 1-3:   Llançament beta pública. Objectiu: 500 usuaris free.
MES 4-6:   Conversió 5% → 25 Starter + 5 Professional = ~275€/mes
MES 7-12:  Creixement orgànic + 2 clients API = ~2.500€/mes

ANY 2 objectiu: 3 clients Enterprise + 200 Pro + 500 Starter = ~20.000€/mes MRR
```

---

## 6. Roadmap de Producte

### Fase 1 — MVP Web (2 mesos)
**Objectiu:** Tenir la plataforma pública amb mapa funcional i registre d'usuaris.

```
Sprint 1 (2 setmanes):
  ├── Landing page pública (Next.js o Vite)
  ├── Integració mapa actual al producte web
  ├── Registre / Login (email + Google OAuth)
  └── Base de dades d'usuaris + plans

Sprint 2 (2 setmanes):
  ├── Fitxa de parcel·la (/parcela/:ref)
  ├── Sistema de límits freemium (rate limiting per usuari)
  ├── Panel "Les meves parcel·les"
  └── Deploy a producció (Railway / Fly.io / VPS)

Sprint 3 (2 setmanes):
  ├── Historial NDVI amb gràfic temporal
  ├── Export CSV bàsic
  └── Pàgina de preus + integració Stripe
```

### Fase 2 — Monetització (1 mes)
```
  ├── Integració Stripe (subscripcions mensuals/anuals)
  ├── Portal de client (gestió de subscripció)
  ├── Generació d'informes PDF per parcel·la
  ├── Sistema d'alertes per email
  └── API keys per a plans Professional i Enterprise
```

### Fase 3 — Creixement (3 mesos)
```
  ├── Cobertura a tota Espanya (no només Catalunya)
  ├── Comparativa temporal (foto aèria vs NDVI)
  ├── Integració amb dades SIGPAC (ús declarat vs real)
  ├── Widget embeddable per a webs de tercers
  └── App mòbil (PWA)
```

---

## 7. Stack Tecnològic Recomanat (Web Pública)

```
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND (web pública)                                     │
│  Next.js 14 (App Router) + TypeScript                       │
│  Tailwind CSS + shadcn/ui                                   │
│  MapLibre GL JS (reutilitzant codi actual)                  │
│  Stripe.js (pagaments)                                      │
├─────────────────────────────────────────────────────────────┤
│  BACKEND (actual FastAPI — ampliar)                         │
│  + Auth: FastAPI Users o Auth.js                            │
│  + Pagaments: Stripe Webhooks                               │
│  + Email: Resend o SendGrid                                 │
│  + Rate limiting: Redis (ja tenim)                          │
├─────────────────────────────────────────────────────────────┤
│  INFRAESTRUCTURA                                            │
│  Producció: Railway.app o Fly.io (senzill, econòmic)        │
│  BD: Neon.tech (PostgreSQL + PostGIS gestionat)             │
│  Fitxers: Cloudflare R2 (imatges Sentinel, exports)         │
│  CDN: Cloudflare (gratis)                                   │
│  Domini: geomap.cat (o agrimap.cat, campcat.cat...)         │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Experiència d'Usuari — User Journeys

### Journey 1: Propietari curiosos (Free → Starter)
```
1. Veu un anunci/article sobre abandó agrícola a Catalunya
2. Entra a geomap.cat → veu el mapa demo
3. Busca el seu municipi → veu les seves parcel·les en gris (sense dades)
   o en color (amb dades) → li genera curiositat
4. Registre gratuït → pot consultar 10 parcel·les/dia
5. Afegeix les seves finques al dashboard
6. Passats 3 dies, rep email: "Hem detectat canvis a la finca 08001A..."
7. Vol veure l'historial → paywall → subscriu Starter (9€/mes)
```

### Journey 2: Gestor/Notari (Professional)
```
1. Client li demana informe de la finca que vol comprar
2. Cerca la referència catastral → veu l'estat actual
3. Vol l'historial dels últims 3 anys → paywall
4. Subscriu Professional (49€/mes) → genera PDF informe
5. Inclou l'informe a l'expedient de compravenda
6. Usa la plataforma per a tots els seus clients → ROI clar
```

### Journey 3: Asseguradora (Enterprise API)
```
1. Necessita verificar l'estat de 50.000 parcel·les assegurades
2. Contacte comercial → demo personalitzada
3. Integra l'API als seus sistemes interns
4. Contracte anual 3.600€/any → estalvia 10x vs inspeccions físiques
```

---

## 9. Mètriques Clau (KPIs)

| Mètrica | Objectiu mes 3 | Objectiu mes 12 |
|---|---|---|
| Usuaris registrats | 500 | 5.000 |
| Conversió Free→Paga | — | 8% |
| MRR (Monthly Recurring Revenue) | 200€ | 5.000€ |
| Parcel·les consultades/dia | 1.000 | 20.000 |
| Churn mensual | — | < 5% |
| NPS | — | > 40 |

---

## 10. Riscos i Mitigació

| Risc | Probabilitat | Impacte | Mitigació |
|---|---|---|---|
| Copernicus canvia l'API | Baixa | Alt | Abstracció de la capa de descàrrega, suport a múltiples fonts |
| Competidor gran (Google, ESRI) | Mitja | Alt | Especialitzar-se en Espanya/Catalunya, dades catastrals úniques |
| Cost infraestructura creix | Mitja | Mitja | Vector tiles, cache agressiu, pagar per ús |
| GDPR / privacitat dades | Baixa | Alt | Les dades catastrals són públiques, no hi ha dades personals |
| Poca conversió a pagament | Mitja | Alt | Testejar preus, millorar onboarding, focus en B2B primer |

---

## 11. Decisions Pendents (Open Questions)

- [ ] **Nom del producte** — GeoMap Agrícola? AgriMap? CampsCat? FieldSight?
- [ ] **Domini** — .cat, .es, .com?
- [ ] **Mercat inicial** — Catalunya only o tot Espanya des del dia 1?
- [ ] **Model de pagament** — Stripe Subscriptions vs pay-per-report?
- [ ] **Autenticació** — Email/password, Google OAuth, o magic link?
- [ ] **Idiomes** — Català, castellà, anglès?
- [ ] **Infraestructura de producció** — Railway vs Fly.io vs VPS propi?

---

## 12. Properes accions (Backlog inicial)

### P0 — Bloqueants (fer ara)
1. Acabar descàrrega parcel·les de Catalunya
2. Executar pipeline NDVI + classificació
3. Verificar que el mapa mostra parcel·les amb colors correctes

### P1 — MVP Web
4. Crear projecte Next.js per a la web pública
5. Migrar/integrar el mapa actual
6. Implementar registre i login d'usuaris
7. Deploy a Railway.app (entorn de proves)

### P2 — Monetització
8. Integrar Stripe (plans i subscripcions)
9. Implementar rate limiting per pla
10. Generador d'informes PDF
11. Sistema d'alertes per email

### P3 — Creixement
12. SEO: pàgines per municipi/comarca
13. Expandir a resta d'Espanya
14. API pública documentada

---

*Document viu — actualitzar a mesura que evolucioni el producte.*
