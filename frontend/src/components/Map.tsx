import { useEffect, useRef, useCallback } from 'react'
import maplibregl, { Map as MapLibreMap, LngLatBoundsLike } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Filters, ParcelStatusProperties } from '../types'
import { fetchParcelStatus, fetchMunicipalitiesGeoJSON } from '../api/client'

const MUNI_SOURCE = 'municipalities'
const MUNI_LAYER_FILL = 'municipalities-fill'
const MUNI_LAYER_OUTLINE = 'municipalities-outline'
const MUNI_SELECTED_SOURCE = 'municipality-selected'
const MUNI_SELECTED_LAYER = 'municipality-selected-outline'

const PARCEL_SOURCE = 'parcels'
const PARCEL_LAYER_FILL = 'parcels-fill'
const PARCEL_LAYER_OUTLINE = 'parcels-outline'

const STATUS_COLOR: Record<string, string> = {
  activa: '#3B6D11',
  abandonada: '#D85A30',
  desconeguda: '#888780',
}

const CATALONIA_BOUNDS: LngLatBoundsLike = [0.15, 40.52, 3.33, 42.86]

// Calcula el bounding box d'una geometria GeoJSON
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getBounds(geometry: any): maplibregl.LngLatBounds {
  const bounds = new maplibregl.LngLatBounds()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function addCoords(coords: any) {
    if (typeof coords[0] === 'number') {
      bounds.extend(coords as [number, number])
    } else {
      coords.forEach(addCoords)
    }
  }
  addCoords(geometry.coordinates)
  return bounds
}

interface MapProps {
  filters: Filters
}

export default function Map({ filters }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const muniDataRef = useRef<any>(null)

  const loadParcels = useCallback(async (map: MapLibreMap) => {
    try {
      const data = await fetchParcelStatus(filters)
      const source = map.getSource(PARCEL_SOURCE) as maplibregl.GeoJSONSource | undefined
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (source) source.setData(data as any)
    } catch (err) {
      console.error('Error carregant parcel·les:', err)
    }
  }, [filters])

  const loadParcelsRef = useRef(loadParcels)
  useEffect(() => { loadParcelsRef.current = loadParcels }, [loadParcels])

  // Inicialitza el mapa una sola vegada
  useEffect(() => {
    if (!containerRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'osm-tiles': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'osm-base', type: 'raster', source: 'osm-tiles' }],
      },
      center: [1.7, 41.8],
      zoom: 7,
    })

    mapRef.current = map

    map.on('load', () => {
      map.fitBounds(CATALONIA_BOUNDS, { padding: 20 })

      // --- Capa tots els municipis ---
      map.addSource(MUNI_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MUNI_LAYER_FILL,
        type: 'fill',
        source: MUNI_SOURCE,
        paint: { 'fill-color': '#2a4a6b', 'fill-opacity': 0.15 },
      })
      map.addLayer({
        id: MUNI_LAYER_OUTLINE,
        type: 'line',
        source: MUNI_SOURCE,
        paint: { 'line-color': '#4a90d9', 'line-width': 0.8, 'line-opacity': 0.6 },
      })

      // --- Capa municipi seleccionat (ressaltat) ---
      map.addSource(MUNI_SELECTED_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: MUNI_SELECTED_LAYER,
        type: 'line',
        source: MUNI_SELECTED_SOURCE,
        paint: { 'line-color': '#ffffff', 'line-width': 2.5, 'line-opacity': 1 },
      })

      // Carrega tots els municipis i guarda'ls en ref
      fetchMunicipalitiesGeoJSON()
        .then((data) => {
          muniDataRef.current = data
          const src = map.getSource(MUNI_SOURCE) as maplibregl.GeoJSONSource
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          src.setData(data as any)
        })
        .catch(console.error)

      // --- Capa parcel·les ---
      map.addSource(PARCEL_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: PARCEL_LAYER_FILL,
        type: 'fill',
        source: PARCEL_SOURCE,
        paint: {
          'fill-color': [
            'match', ['get', 'status'],
            'activa', STATUS_COLOR.activa,
            'abandonada', STATUS_COLOR.abandonada,
            STATUS_COLOR.desconeguda,
          ],
          'fill-opacity': [
            'case',
            ['==', ['get', 'status'], 'desconeguda'], 0.5,
            ['interpolate', ['linear'],
              ['coalesce', ['get', 'confidence'], 0.5],
              0, 0.5, 1, 0.9,
            ],
          ],
        },
      })
      map.addLayer({
        id: PARCEL_LAYER_OUTLINE,
        type: 'line',
        source: PARCEL_SOURCE,
        paint: { 'line-color': '#ffffff', 'line-width': 0.5, 'line-opacity': 0.4 },
      })

      // Popup en click sobre parcel·la
      map.on('click', PARCEL_LAYER_FILL, (e) => {
        const feature = e.features?.[0]
        if (!feature) return
        const props = feature.properties as ParcelStatusProperties
        new maplibregl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(`
            <div style="font-family:system-ui;font-size:13px;line-height:1.5">
              <strong>${props.ref_catastral}</strong><br/>
              Estat: <b style="color:${STATUS_COLOR[props.status] ?? '#888'}">${props.status}</b><br/>
              Confiança: ${Math.round((props.confidence ?? 0) * 100)}%
            </div>
          `)
          .addTo(map)
      })
      map.on('mouseenter', PARCEL_LAYER_FILL, () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', PARCEL_LAYER_FILL, () => { map.getCanvas().style.cursor = '' })

      loadParcelsRef.current(map)
      map.on('moveend', () => loadParcelsRef.current(map))
    })

    return () => map.remove()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Reacciona als canvis de filtres: zoom + ressaltat + recàrrega parcel·les
  useEffect(() => {
    const map = mapRef.current
    if (!map?.isStyleLoaded()) return

    const selectedSrc = map.getSource(MUNI_SELECTED_SOURCE) as maplibregl.GeoJSONSource | undefined

    if (filters.municipalityId && muniDataRef.current) {
      // Troba el feature del municipi seleccionat
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const feature = muniDataRef.current.features.find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (f: any) => f.properties.id === filters.municipalityId
      )
      if (feature) {
        // Ressalta el contorn
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        selectedSrc?.setData({ type: 'FeatureCollection', features: [feature] } as any)
        // Zoom al municipi
        const bounds = getBounds(feature.geometry)
        if (!bounds.isEmpty()) {
          map.fitBounds(bounds, { padding: 60, maxZoom: 14, duration: 800 })
        }
      }
    } else {
      // Cap municipi seleccionat → esborra ressaltat i torna a Catalunya
      selectedSrc?.setData({ type: 'FeatureCollection', features: [] } as any)
      if (!filters.municipalityId) {
        map.fitBounds(CATALONIA_BOUNDS, { padding: 20, duration: 800 })
      }
    }

    loadParcels(map)
  }, [filters, loadParcels])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
      aria-label="Mapa de parcel·les agrícoles de Catalunya"
    />
  )
}
