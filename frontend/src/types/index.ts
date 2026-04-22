export type ParcelStatus = 'activa' | 'abandonada' | 'desconeguda'

export interface ParcelProperties {
  id: number
  ref_catastral: string
  municipality_id: number
  superficie_ha: number | null
  uso_sigpac: string | null
}

export interface ParcelStatusProperties {
  parcel_id: number
  ref_catastral: string
  status: ParcelStatus
  confidence: number
  algoritmo_version: string
  calculated_at: string | null
}

export interface GeoFeature<P> {
  type: 'Feature'
  geometry: GeoJSON.Geometry
  properties: P
}

export interface GeoFeatureCollection<P> {
  type: 'FeatureCollection'
  features: GeoFeature<P>[]
  total: number
}

export interface Municipality {
  id: number
  name: string
  code_ine: string
  province: string | null
  area_km2: number | null
}

export interface MunicipalityList {
  items: Municipality[]
  total: number
}

export interface Filters {
  municipalityId: number | null
  status: ParcelStatus | null
  minSuperficieHa: number | null
  maxSuperficieHa: number | null
}
