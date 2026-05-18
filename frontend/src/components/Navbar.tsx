import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const PLAN_BADGE: Record<string, string> = {
  free: 'Free',
  starter: 'Starter',
  professional: 'Pro',
  enterprise: 'Enterprise',
}

export default function Navbar() {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isMap = pathname === '/mapa'

  return (
    <nav style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 32px', height: 56, background: '#0f3460', color: 'white',
      flexShrink: 0, zIndex: 100,
    }}>
      <Link to="/" style={{ textDecoration: 'none', color: 'white', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 20 }}>🌾</span>
        <span style={{ fontWeight: 800, fontSize: 17, letterSpacing: '-0.3px' }}>GeoMap Agrícola</span>
      </Link>

      <div style={{ display: 'flex', alignItems: 'center', gap: 24, fontSize: 14 }}>
        <Link to="/mapa" style={{ color: 'rgba(255,255,255,0.85)', textDecoration: 'none', fontWeight: isMap ? 600 : 400 }}>
          Mapa
        </Link>
        <a href="#preus" style={{ color: 'rgba(255,255,255,0.85)', textDecoration: 'none' }}>Preus</a>

        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Link to="/compte" style={{
              fontSize: 12, color: 'rgba(255,255,255,0.7)', textDecoration: 'none',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {user.email}
            </Link>
            <Link to="/compte" style={{
              background: 'rgba(232,184,75,0.25)', color: '#e8b84b',
              padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
              textDecoration: 'none',
            }}>
              {PLAN_BADGE[user.plan]}
            </Link>
            <button
              onClick={() => { logout(); navigate('/') }}
              style={{
                background: 'rgba(255,255,255,0.12)', color: 'white',
                border: '1px solid rgba(255,255,255,0.2)',
                padding: '5px 14px', borderRadius: 20, fontSize: 12, cursor: 'pointer',
              }}
            >
              Sortir
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Link to="/login" style={{ color: 'rgba(255,255,255,0.85)', textDecoration: 'none', fontSize: 13 }}>
              Entrar
            </Link>
            <Link to="/register" style={{
              background: '#e8b84b', color: '#1a1a2e', padding: '7px 18px',
              borderRadius: 20, fontWeight: 700, textDecoration: 'none', fontSize: 13,
            }}>
              Prova gratuïta
            </Link>
          </div>
        )}
      </div>
    </nav>
  )
}
