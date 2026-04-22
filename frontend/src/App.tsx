import { useState } from 'react'
import Map from './components/Map'
import FilterPanel from './components/FilterPanel'
import type { Filters } from './types'
import './App.css'

const DEFAULT_FILTERS: Filters = {
  municipalityId: null,
  status: null,
  minSuperficieHa: null,
  maxSuperficieHa: null,
}

export default function App() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)

  return (
    <div className="app">
      <Map filters={filters} />
      <FilterPanel filters={filters} onChange={setFilters} />
    </div>
  )
}
