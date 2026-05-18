import { useState, useCallback } from 'react'
import Map from '../components/Map'
import FilterPanel from '../components/FilterPanel'
import Navbar from '../components/Navbar'
import ParcelDetailPanel from '../components/ParcelDetailPanel'
import type { Filters } from '../types'

const DEFAULT_FILTERS: Filters = {
  municipalityId: null,
  status: null,
  minSuperficieHa: null,
  maxSuperficieHa: null,
}

export default function MapPage() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [selectedRef, setSelectedRef] = useState<string | null>(null)

  const handleParcelClick = useCallback((ref: string) => setSelectedRef(ref), [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Navbar />
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <Map filters={filters} onParcelClick={handleParcelClick} />
        <FilterPanel filters={filters} onChange={setFilters} />
        <ParcelDetailPanel refCatastral={selectedRef} onClose={() => setSelectedRef(null)} />
      </div>
    </div>
  )
}
