import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchUsage, type UsageInfo } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Navbar from '../components/Navbar'

const PLAN_LABEL: Record<string, string> = {
  free: 'Free',
  starter: 'Starter',
  professional: 'Professional',
  enterprise: 'Enterprise',
}

const PLAN_COLOR: Record<string, string> = {
  free: '#888',
  starter: '#4caf50',
  professional: '#0f3460',
  enterprise: '#e8b84b',
}

const UPGRADE_PLANS = [
  { key: 'starter', name: 'Starter', price: '9€/mes', features: ['Il·limitades', 'Historial 1 any', '5 informes PDF'] },
  { key: 'professional', name: 'Professional', price: '49€/mes', features: ['Tot il·limitat', 'Historial 3 anys', 'API access'], highlight: true },
]

export default function Account() {
  const { user, token, logout } = useAuth()
  const navigate = useNavigate()
  const [usage, setUsage] = useState<UsageInfo | null>(null)

  useEffect(() => {
    if (!user || !token) { navigate('/login'); return }
    fetchUsage(token).then(setUsage).catch(console.error)
  }, [user, token, navigate])

  if (!user) return null

  const isFree = user.plan === 'free'
  const pct = usage && usage.daily_limit
    ? Math.round((usage.queries_used_today / usage.daily_limit) * 100)
    : 0

  return (
    <div style={{ minHeight: '100vh', background: '#f8f9fa', fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
      <Navbar />
      <div style={{ maxWidth: 640, margin: '0 auto', padding: '40px 24px' }}>

        {/* Capçalera */}
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: '#1a1a2e', margin: 0 }}>El meu compte</h1>
          <p style={{ color: '#888', marginTop: 6, fontSize: 14 }}>{user.email}</p>
        </div>

        {/* Targeta pla */}
        <div style={{
          background: 'white', borderRadius: 14, padding: 28,
          boxShadow: '0 2px 12px rgba(0,0,0,0.06)', marginBottom: 20,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 12, color: '#999', marginBottom: 6 }}>Pla actual</div>
              <div style={{
                display: 'inline-block', background: PLAN_COLOR[user.plan],
                color: 'white', padding: '4px 14px', borderRadius: 20,
                fontWeight: 700, fontSize: 14,
              }}>
                {PLAN_LABEL[user.plan]}
              </div>
            </div>
            {isFree && (
              <a href="#upgrade" style={{
                background: '#e8b84b', color: '#1a1a2e',
                padding: '8px 18px', borderRadius: 8, fontWeight: 700,
                fontSize: 13, textDecoration: 'none',
              }}>
                Fer upgrade
              </a>
            )}
          </div>

          {/* Barra d'ús (només free) */}
          {isFree && usage && (
            <div style={{ marginTop: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8 }}>
                <span style={{ color: '#555' }}>Consultes avui</span>
                <span style={{ fontWeight: 700, color: pct >= 100 ? '#c62828' : '#333' }}>
                  {usage.queries_used_today} / {usage.daily_limit}
                </span>
              </div>
              <div style={{ background: '#f0f0f0', borderRadius: 8, height: 10, overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.min(pct, 100)}%`, height: '100%', borderRadius: 8,
                  background: pct >= 100 ? '#c62828' : pct >= 70 ? '#e8b84b' : '#4caf50',
                  transition: 'width 0.4s',
                }} />
              </div>
              {pct >= 100 && (
                <div style={{ marginTop: 8, fontSize: 12, color: '#c62828' }}>
                  Límit assolit. Es reinicia a les 00:00.
                </div>
              )}
              {pct < 100 && (
                <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
                  {usage.queries_remaining} consultes restants avui
                </div>
              )}
            </div>
          )}

          {!isFree && (
            <div style={{ marginTop: 16, fontSize: 13, color: '#4caf50', fontWeight: 600 }}>
              ✓ Consultes il·limitades
            </div>
          )}
        </div>

        {/* Botó tancar sessió */}
        <button
          onClick={() => { logout(); navigate('/') }}
          style={{
            background: 'white', color: '#c62828', border: '1px solid #ffcdd2',
            padding: '10px 20px', borderRadius: 8, fontWeight: 600,
            fontSize: 13, cursor: 'pointer', width: '100%', marginBottom: 32,
          }}
        >
          Tancar sessió
        </button>

        {/* Upgrade (només free) */}
        {isFree && (
          <div id="upgrade">
            <h2 style={{ fontSize: 18, fontWeight: 800, color: '#1a1a2e', marginBottom: 16 }}>
              Escala el teu pla
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {UPGRADE_PLANS.map(plan => (
                <div key={plan.key} style={{
                  background: plan.highlight ? '#0f3460' : 'white',
                  color: plan.highlight ? 'white' : '#1a1a2e',
                  borderRadius: 14, padding: 24,
                  boxShadow: plan.highlight
                    ? '0 8px 32px rgba(15,52,96,0.25)'
                    : '0 2px 12px rgba(0,0,0,0.06)',
                }}>
                  <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 4 }}>{plan.name}</div>
                  <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 16, color: plan.highlight ? '#e8b84b' : '#0f3460' }}>
                    {plan.price}
                  </div>
                  <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 20px', fontSize: 13 }}>
                    {plan.features.map(f => (
                      <li key={f} style={{ padding: '4px 0', opacity: 0.85 }}>
                        <span style={{ color: plan.highlight ? '#e8b84b' : '#4caf50', marginRight: 6 }}>✓</span>{f}
                      </li>
                    ))}
                  </ul>
                  <button style={{
                    width: '100%', padding: '9px 0', borderRadius: 8,
                    border: 'none', fontWeight: 700, fontSize: 13, cursor: 'pointer',
                    background: plan.highlight ? '#e8b84b' : '#f0f4ff',
                    color: plan.highlight ? '#1a1a2e' : '#0f3460',
                  }}>
                    Prova 14 dies gratis
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
