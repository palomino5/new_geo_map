import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchParcelPublic, type NdviPoint, type ParcelPublic } from '../api/client'
import Navbar from '../components/Navbar'

const STATUS_COLOR: Record<string, string> = {
  activa: '#3B6D11',
  abandonada: '#D85A30',
  desconeguda: '#888780',
}
const STATUS_LABEL: Record<string, string> = {
  activa: '🟢 Activa',
  abandonada: '🔴 Abandonada',
  desconeguda: '⚪ Desconeguda',
}
const STATUS_DESC: Record<string, string> = {
  activa: 'Aquesta parcel·la mostra activitat agrícola recent detectada per satèl·lit.',
  abandonada: 'Aquesta parcel·la presenta índexs de vegetació consistentment baixos durant l\'últim any.',
  desconeguda: 'No hi ha prou dades satelitals per classificar aquesta parcel·la amb certesa.',
}

function MiniNdviChart({ data }: { data: NdviPoint[] }) {
  if (data.length === 0) return null
  const W = 280, H = 90, PAD = { top: 8, right: 8, bottom: 20, left: 28 }
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const xStep = innerW / (data.length - 1 || 1)
  const toX = (i: number) => PAD.left + i * xStep
  const toY = (v: number) => PAD.top + innerH - v * innerH
  const linePath = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toY(d.ndvi_mean)}`).join(' ')

  return (
    <svg width={W} height={H} style={{ overflow: 'visible' }}>
      {[0, 0.3, 0.6, 1].map(v => (
        <g key={v}>
          <line x1={PAD.left} y1={toY(v)} x2={W - PAD.right} y2={toY(v)} stroke="#eee" strokeWidth={1} />
          <text x={PAD.left - 4} y={toY(v) + 4} textAnchor="end" fontSize={8} fill="#bbb">{v}</text>
        </g>
      ))}
      <rect x={PAD.left} y={toY(0.3)} width={innerW} height={toY(0) - toY(0.3)} fill="rgba(59,109,17,0.06)" />
      <path d={linePath} fill="none" stroke="#3B6D11" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => (
        <circle key={i} cx={toX(i)} cy={toY(d.ndvi_mean)} r={3} fill="#3B6D11" />
      ))}
      {data.map((d, i) => (
        <text key={i} x={toX(i)} y={H - 2} textAnchor="middle" fontSize={8} fill="#bbb">
          {d.date.slice(5)}
        </text>
      ))}
    </svg>
  )
}

export default function ParcelPage() {
  const { refCatastral } = useParams<{ refCatastral: string }>()
  const [parcel, setParcel] = useState<ParcelPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!refCatastral) return
    setLoading(true)
    fetchParcelPublic(refCatastral)
      .then(setParcel)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [refCatastral])

  return (
    <div style={{ minHeight: '100vh', background: '#f8f9fa', fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
      <Navbar />

      <div style={{ maxWidth: 680, margin: '0 auto', padding: '40px 24px' }}>
        {loading && (
          <div style={{ textAlign: 'center', color: '#aaa', padding: 80 }}>Carregant...</div>
        )}

        {notFound && (
          <div style={{ textAlign: 'center', padding: 80 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
            <h2 style={{ color: '#333' }}>Parcel·la no trobada</h2>
            <p style={{ color: '#888' }}>La referència catastral <code>{refCatastral}</code> no existeix a la base de dades.</p>
            <Link to="/mapa" style={{ color: '#0f3460', fontWeight: 700 }}>← Tornar al mapa</Link>
          </div>
        )}

        {parcel && !loading && (
          <>
            {/* Breadcrumb */}
            <div style={{ fontSize: 13, color: '#999', marginBottom: 24 }}>
              <Link to="/" style={{ color: '#999', textDecoration: 'none' }}>GeoMap</Link>
              {' › '}
              <Link to="/mapa" style={{ color: '#999', textDecoration: 'none' }}>Mapa</Link>
              {' › '}
              {parcel.municipality_name}
              {' › '}
              <span style={{ color: '#555' }}>{parcel.ref_catastral}</span>
            </div>

            {/* Capçalera */}
            <div style={{
              background: 'white', borderRadius: 16, padding: 32,
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', marginBottom: 20,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
                <div>
                  <div style={{ fontSize: 12, color: '#999', marginBottom: 6 }}>Referència catastral</div>
                  <h1 style={{ fontSize: 20, fontWeight: 800, fontFamily: 'monospace', color: '#1a1a2e', margin: 0 }}>
                    {parcel.ref_catastral}
                  </h1>
                  <div style={{ fontSize: 14, color: '#888', marginTop: 6 }}>{parcel.municipality_name}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{
                    display: 'inline-block',
                    background: STATUS_COLOR[parcel.status] + '18',
                    color: STATUS_COLOR[parcel.status],
                    padding: '6px 16px', borderRadius: 20, fontWeight: 700, fontSize: 14,
                  }}>
                    {STATUS_LABEL[parcel.status] ?? parcel.status}
                  </div>
                  <div style={{ fontSize: 12, color: '#aaa', marginTop: 6 }}>
                    Confiança: {Math.round(parcel.confidence * 100)}%
                  </div>
                </div>
              </div>

              <p style={{ fontSize: 14, color: '#666', marginTop: 20, lineHeight: 1.7, borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
                {STATUS_DESC[parcel.status]}
              </p>
            </div>

            {/* Info grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'Superfície', value: parcel.superficie_ha ? `${parcel.superficie_ha.toFixed(2)} ha` : '—' },
                { label: 'Ús SIGPAC', value: parcel.uso_sigpac ?? '—' },
                { label: 'Municipi', value: parcel.municipality_name },
                { label: 'Actualitzat', value: parcel.calculated_at ? parcel.calculated_at.slice(0, 10) : '—' },
              ].map(({ label, value }) => (
                <div key={label} style={{
                  background: 'white', borderRadius: 12, padding: '16px 20px',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
                }}>
                  <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>{label}</div>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>{value}</div>
                </div>
              ))}
            </div>

            {/* NDVI preview */}
            <div style={{
              background: 'white', borderRadius: 16, padding: 28,
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', marginBottom: 20,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, color: '#1a1a2e' }}>Historial NDVI</div>
                  <div style={{ fontSize: 12, color: '#999', marginTop: 2 }}>
                    {parcel.ndvi_total_count} observacions totals
                  </div>
                </div>
                {parcel.ndvi_total_count > 3 && (
                  <div style={{
                    background: '#fff8e6', border: '1px solid #e8b84b',
                    borderRadius: 8, padding: '4px 12px', fontSize: 12, color: '#b8860b',
                  }}>
                    Mostrant les últimes 3
                  </div>
                )}
              </div>

              {parcel.ndvi_preview.length > 0 ? (
                <MiniNdviChart data={[...parcel.ndvi_preview].reverse()} />
              ) : (
                <div style={{ color: '#aaa', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
                  Sense dades NDVI disponibles
                </div>
              )}

              {/* CTA historial complet */}
              {parcel.ndvi_total_count > 0 && (
                <div style={{
                  marginTop: 20, padding: '16px 20px', borderRadius: 10,
                  background: 'linear-gradient(135deg, #0f3460, #16213e)',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
                }}>
                  <div>
                    <div style={{ color: 'white', fontWeight: 700, fontSize: 14 }}>
                      Veure historial complet
                    </div>
                    <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, marginTop: 2 }}>
                      {parcel.ndvi_total_count} observacions · Gràfic interactiu · Export CSV
                    </div>
                  </div>
                  <Link to="/register" style={{
                    background: '#e8b84b', color: '#1a1a2e',
                    padding: '9px 18px', borderRadius: 8, fontWeight: 700,
                    fontSize: 13, textDecoration: 'none', whiteSpace: 'nowrap',
                  }}>
                    Registre gratuït →
                  </Link>
                </div>
              )}
            </div>

            {/* Botó compartir */}
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button
                onClick={() => navigator.clipboard.writeText(window.location.href)}
                style={{
                  background: 'white', border: '1px solid #e0e0e0',
                  padding: '10px 20px', borderRadius: 8, fontSize: 13,
                  fontWeight: 600, cursor: 'pointer', color: '#555',
                }}
              >
                📋 Copiar URL
              </button>
              <Link to="/mapa" style={{
                background: '#0f3460', color: 'white',
                padding: '10px 20px', borderRadius: 8, fontSize: 13,
                fontWeight: 600, textDecoration: 'none',
              }}>
                🗺️ Veure al mapa
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
