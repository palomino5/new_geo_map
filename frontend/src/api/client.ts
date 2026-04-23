import type { GeoFeatureCollection, MunicipalityList, Municipality, ParcelProperties, ParcelStatusProperties, Filters } from '../types'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function fetchJson<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export async function fetchMunicipalities(): Promise<Municipality[]> {
  const data = await fetchJson<MunicipalityList>('/municipalities')
  return data.items
}

export async function fetchMunicipalitiesGeoJSON(): Promise<object> {
  return fetchJson<object>('/municipalities/geojson')
}

export async function fetchParcels(
  bbox: [number, number, number, number],
  filters: Filters,
): Promise<GeoFeatureCollection<ParcelProperties>> {
  const params: Record<string, string> = {
    bbox: bbox.join(','),
    limit: '1000',
  }
  if (filters.municipalityId !== null) {
    params.municipality_id = String(filters.municipalityId)
  }
  return fetchJson<GeoFeatureCollection<ParcelProperties>>('/parcels', params)
}

export async function fetchParcelStatus(
  filters: Filters,
): Promise<GeoFeatureCollection<ParcelStatusProperties>> {
  const params: Record<string, string> = { limit: '2000' }
  if (filters.municipalityId !== null) params.municipality_id = String(filters.municipalityId)
  if (filters.status !== null) params.status = filters.status
  return fetchJson<GeoFeatureCollection<ParcelStatusProperties>>('/parcels/status', params)
}
