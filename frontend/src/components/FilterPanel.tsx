import { useEffect, useState } from 'react'
import type { Filters, Municipality, ParcelStatus } from '../types'
import { fetchMunicipalities } from '../api/client'
import styles from './FilterPanel.module.css'

interface FilterPanelProps {
  filters: Filters
  onChange: (filters: Filters) => void
}

const STATUS_OPTIONS: { value: ParcelStatus | ''; label: string }[] = [
  { value: '', label: 'Tots els estats' },
  { value: 'activa', label: 'Activa' },
  { value: 'abandonada', label: 'Abandonada' },
  { value: 'desconeguda', label: 'Desconeguda' },
]

export default function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [municipalities, setMunicipalities] = useState<Municipality[]>([])

  useEffect(() => {
    fetchMunicipalities()
      .then(setMunicipalities)
      .catch(console.error)
  }, [])

  if (collapsed) {
    return (
      <button className={styles.toggleBtn} onClick={() => setCollapsed(false)} aria-label="Expandir filtres">
        ☰
      </button>
    )
  }

  return (
    <aside className={styles.panel}>
      <div className={styles.header}>
        <h2 className={styles.title}>Filtres</h2>
        <button className={styles.collapseBtn} onClick={() => setCollapsed(true)} aria-label="Col·lapsar filtres">
          ✕
        </button>
      </div>

      <div className={styles.section}>
        <label className={styles.label} htmlFor="municipality-select">Municipi</label>
        <select
          id="municipality-select"
          className={styles.select}
          value={filters.municipalityId ?? ''}
          onChange={(e) =>
            onChange({ ...filters, municipalityId: e.target.value ? Number(e.target.value) : null })
          }
        >
          <option value="">Tots els municipis</option>
          {municipalities.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.section}>
        <label className={styles.label} htmlFor="status-select">Estat de la parcel·la</label>
        <select
          id="status-select"
          className={styles.select}
          value={filters.status ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              status: e.target.value ? (e.target.value as ParcelStatus) : null,
            })
          }
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.section}>
        <label className={styles.label}>Superfície (ha)</label>
        <div className={styles.rangeRow}>
          <input
            type="number"
            className={styles.input}
            placeholder="Mínim"
            min={0}
            value={filters.minSuperficieHa ?? ''}
            onChange={(e) =>
              onChange({ ...filters, minSuperficieHa: e.target.value ? Number(e.target.value) : null })
            }
          />
          <span className={styles.rangeSep}>—</span>
          <input
            type="number"
            className={styles.input}
            placeholder="Màxim"
            min={0}
            value={filters.maxSuperficieHa ?? ''}
            onChange={(e) =>
              onChange({ ...filters, maxSuperficieHa: e.target.value ? Number(e.target.value) : null })
            }
          />
        </div>
      </div>

      <div className={styles.legend}>
        <div className={styles.legendTitle}>Llegenda</div>
        <div className={styles.legendItem}>
          <span className={styles.dot} style={{ background: '#3B6D11' }} />
          Activa
        </div>
        <div className={styles.legendItem}>
          <span className={styles.dot} style={{ background: '#D85A30' }} />
          Abandonada
        </div>
        <div className={styles.legendItem}>
          <span className={styles.dot} style={{ background: '#888780' }} />
          Desconeguda
        </div>
      </div>

      <button
        className={styles.resetBtn}
        onClick={() =>
          onChange({ municipalityId: null, status: null, minSuperficieHa: null, maxSuperficieHa: null })
        }
      >
        Restablir filtres
      </button>
    </aside>
  )
}
