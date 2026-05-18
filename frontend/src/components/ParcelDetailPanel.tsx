import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchParcelDetail, type ParcelDetail } from '../api/client'
import { useAuth } from '../context/AuthContext'

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

function NdviChart({ data }: { data: ParcelDetail['ndvi_history'] }) {
  if (data.length === 0) return (
    <div style={{ textAlign: 'center', color: '#aaa', fontSize: 13, padding: '24px 0' }}>
      Sense dades NDVI disponibles
    </div>
  )

  const W = 300, H = 120, PAD = { top: 10, right: 10, bottom: 24, left: 32 }
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  const minVal = 0
  const maxVal = 1
  const xStep = innerW / (data.length - 1 || 1)

  const toX = (i: number) => PAD.left + i * xStep
  const toY = (v: number) => PAD.top + innerH - ((v - minVal) / (maxVal - minVal)) * innerH

  const linePath = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toY(d.ndvi_mean)}`).join(' ')

  const areaPath = [
    ...data.map((d, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toY(d.ndvi_max ?? d.ndvi_mean)}`),
    ...data.map((d, i) => `L${toX(data.length - 1 - i)},${toY(data[data.length - 1 - i].ndvi_min ?? data[data.length - 1 - i].ndvi_mean)}`),
    'Z',
  ].join(' ')

  const yLines = [0, 0.15, 0.3, 0.5, 0.7, 1]

  return (
    <svg width={W} height={H} style={{ overflow: 'visible' }}>
      {/* Grid */}
      {yLines.map(v => (
        <g key={v}>
          <line x1={PAD.left} y1={toY(v)} x2={W - PAD.right} y2={toY(v)} stroke="#eee" strokeWidth={1} />
          <text x={PAD.left - 4} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="#aaa">{v}</text>
        </g>
      ))}
      {/* Zones de referència */}
      <rect x={PAD.left} y={toY(0.3)} width={innerW} height={toY(0) - toY(0.3)} fill="rgba(59,109,17,0.06)" />
      <rect x={PAD.left} y={toY(0.15)} width={innerW} height={toY(0) - toY(0.15)} fill="rgba(216,90,48,0.06)" />
      {/* Àrea min-max */}
      <path d={areaPath} fill="rgba(59,109,17,0.15)" />
      {/* Línia NDVI mitjà */}
      <path d={linePath} fill="none" stroke="#3B6D11" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {/* Punts */}
      {data.map((d, i) => (
        <circle key={i} cx={toX(i)} cy={toY(d.ndvi_mean)} r={3} fill="#3B6D11" />
      ))}
      {/* Eix X: dates cada N punts */}
      {data.filter((_, i) => i % Math.ceil(data.length / 4) === 0 || i === data.length - 1).map((d, _, arr) => {
        const origIdx = data.indexOf(d)
        return (
          <text key={d.date} x={toX(origIdx)} y={H - 4} textAnchor="middle" fontSize={9} fill="#aaa">
            {d.date.slice(5)}
          </text>
        )
      })}
    </svg>
  )
}

function ctaBtnStyle(bg: string, color = 'white'): React.CSSProperties {
  return {
    background: bg, color, border: 'none', borderRadius: 8,
    padding: '9px 20px', fontWeight: 700, fontSize: 13,
    cursor: 'pointer', width: '100%',
  }
}

interface Props {
  refCatastral: string | null
  onClose: () => void
}

export default function ParcelDetailPanel({ refCatastral, onClose }: Props) {
  const { token } = useAuth()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ParcelDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ status: number; message: string } | null>(null)

  useEffect(() => {
    if (!refCatastral) { setDetail(null); setError(null); return }
    if (!token) { setError({ status: 401, message: 'Cal iniciar sessió per consultar detalls' }); return }
    setLoading(true)
    setError(null)
    fetchParcelDetail(refCatastral, token)
      .then(d => { setDetail(d); setError(null) })
      .catch((err: Error & { status?: number }) => {
        setDetail(null)
        setError({ status: err.status ?? 0, message: err.message })
      })
      .finally(() => setLoading(false))
  }, [refCatastral, token])

  if (!refCatastral) return null

  return (
    <div style={{
      position: 'absolute', bottom: 0, right: 0,
      width: 340, maxHeight: '70vh',
      background: 'white', borderRadius: '12px 0 0 0',
      boxShadow: '-4px -4px 24px rgba(0,0,0,0.12)',
      display: 'flex', flexDirection: 'column',
      zIndex: 10, overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 16px', background: '#0f3460', color: 'white',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>Referència catastral</div>
          <div style={{ fontWeight: 700, fontSize: 13, fontFamily: 'monospace' }}>{refCatastral}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Link
            to={`/parcela/${refCatastral}`}
            target="_blank"
            title="Veure fitxa pública"
            style={{ color: 'rgba(255,255,255,0.7)', fontSize: 16, lineHeight: 1, padding: 4, textDecoration: 'none' }}
          >
            ↗
          </Link>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: 'white',
            fontSize: 20, cursor: 'pointer', lineHeight: 1, padding: 4,
          }}>×</button>
        </div>
      </div>

      {loading && (
        <div style={{ padding: 24, textAlign: 'center', color: '#aaa', fontSize: 13 }}>Carregant...</div>
      )}

      {error && !loading && (
        <div style={{ padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
          {error.status === 401 ? (
            <>
              <div style={{ fontSize: 28 }}>🔒</div>
              <div style={{ fontSize: 14, color: '#555' }}>Cal iniciar sessió per veure els detalls de la parcel·la</div>
              <button onClick={() => navigate('/login')} style={ctaBtnStyle('#0f3460')}>
                Iniciar sessió
              </button>
              <button onClick={() => navigate('/register')} style={ctaBtnStyle('#e8b84b', '#1a1a2e')}>
                Registre gratuït
              </button>
            </>
          ) : error.status === 429 ? (
            <>
              <div style={{ fontSize: 28 }}>⚡</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#333' }}>Límit diari assolit</div>
              <div style={{ fontSize: 13, color: '#666' }}>Has fet les 10 consultes gratuïtes d'avui</div>
              <button onClick={() => navigate('/compte')} style={ctaBtnStyle('#e8b84b', '#1a1a2e')}>
                Veure plans →
              </button>
            </>
          ) : (
            <div style={{ fontSize: 13, color: '#c62828' }}>{error.message}</div>
          )}
        </div>
      )}

      {detail && !loading && (
        <div style={{ overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Estat */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>Estat actual</div>
              <div style={{ fontWeight: 700, fontSize: 15, color: STATUS_COLOR[detail.status] }}>
                {STATUS_LABEL[detail.status]}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>Confiança</div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>{Math.round(detail.confidence * 100)}%</div>
            </div>
          </div>

          {/* Info */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: 'Municipi', value: detail.municipality_name },
              { label: 'Superfície', value: detail.superficie_ha ? `${detail.superficie_ha.toFixed(2)} ha` : '—' },
              { label: 'Ús SIGPAC', value: detail.uso_sigpac ?? '—' },
              { label: 'Actualitzat', value: detail.calculated_at ? detail.calculated_at.slice(0, 10) : '—' },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#f8f9fa', borderRadius: 8, padding: '8px 12px' }}>
                <div style={{ fontSize: 10, color: '#999', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{value}</div>
              </div>
            ))}
          </div>

          {/* Gràfic NDVI */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#444', marginBottom: 8 }}>
              Historial NDVI ({detail.ndvi_history.length} observacions)
            </div>
            <NdviChart data={detail.ndvi_history} />
            <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11, color: '#aaa' }}>
              <span style={{ color: 'rgba(59,109,17,0.5)' }}>■</span> &gt;0.3 activa
              <span style={{ color: 'rgba(216,90,48,0.5)' }}>■</span> &lt;0.15 abandonada
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
