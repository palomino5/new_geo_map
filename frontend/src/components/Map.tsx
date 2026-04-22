import { useEffect, useRef, useCallback } from 'react'
import maplibregl, { Map as MapLibreMap, LngLatBoundsLike } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Filters, ParcelStatusProperties } from '../types'
import { fetchParcelStatus } from '../api/client'

const PARCEL_SOURCE = 'parcels'
const PARCEL_LAYER_FILL = 'parcels-fill'
const PARCEL_LAYER_OUTLINE = 'parcels-outline'

const STATUS_COLOR: Record<string, string> = {
  activa: '#3B6D11',
  abandonada: '#D85A30',
  desconeguda: '#888780',
}

const CATALONIA_BOUNDS: LngLatBoundsLike = [0.15, 40.52, 3.33, 42.86]

interface MapProps {
  filters: Filters
}

export default function Map({ filters }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)

  const loadParcels = useCallback(async (map: MapLibreMap) => {
    try {
      const data = await fetchParcelStatus(filters)
      const source = map.getSource(PARCEL_SOURCE) as maplibregl.GeoJSONSource | undefined
      if (source) {
        source.setData(data as GeoJSON.FeatureCollection)
      }
    } catch (err) {
      console.error('Error carregant parcel·les:', err)
    }
  }, [filters])

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
        layers: [
          {
            id: 'osm-base',
            type: 'raster',
            source: 'osm-tiles',
          },
        ],
      },
      center: [1.7, 41.8],
      zoom: 7,
    })

    mapRef.current = map

    map.on('load', () => {
      map.fitBounds(CATALONIA_BOUNDS, { padding: 20 })

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
            'match',
            ['get', 'status'],
            'activa', STATUS_COLOR.activa,
            'abandonada', STATUS_COLOR.abandonada,
            STATUS_COLOR.desconeguda,
          ],
          'fill-opacity': [
            'interpolate',
            ['linear'],
            ['coalesce', ['get', 'confidence'], 0.5],
            0, 0.2,
            1, 0.8,
          ],
        },
      })

      map.addLayer({
        id: PARCEL_LAYER_OUTLINE,
        type: 'line',
        source: PARCEL_SOURCE,
        paint: {
          'line-color': '#ffffff',
          'line-width': 0.5,
          'line-opacity': 0.4,
        },
      })

      // Popup en click
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
              Confiança: ${Math.round((props.confidence ?? 0) * 100)}%<br/>
              Versió: ${props.algoritmo_version}
            </div>
          `)
          .addTo(map)
      })

      map.on('mouseenter', PARCEL_LAYER_FILL, () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', PARCEL_LAYER_FILL, () => {
        map.getCanvas().style.cursor = ''
      })

      // Carrega inicial i en cada moviment
      loadParcels(map)
      map.on('moveend', () => loadParcels(map))
    })

    return () => map.remove()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Recarrega quan canvien els filtres
  useEffect(() => {
    if (mapRef.current?.isStyleLoaded()) {
      loadParcels(mapRef.current)
    }
  }, [filters, loadParcels])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
      aria-label="Mapa de parcel·les agrícoles de Catalunya"
    />
  )
}
