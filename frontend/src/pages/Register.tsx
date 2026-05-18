import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (password !== password2) { setError('Les contrasenyes no coincideixen'); return }
    if (password.length < 8) { setError('La contrasenya ha de tenir mínim 8 caràcters'); return }
    setLoading(true)
    try {
      await register(email, password)
      navigate('/mapa')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconegut')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0f3460 0%, #16213e 60%, #1a4a2e 100%)',
    }}>
      <div style={{
        background: 'white', borderRadius: 16, padding: '40px 36px',
        width: '100%', maxWidth: 400, boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🌾</div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0f3460', margin: 0 }}>GeoMap Agrícola</h1>
          <p style={{ color: '#999', fontSize: 14, marginTop: 6 }}>Crea el teu compte gratuït</p>
        </div>

        <div style={{
          background: '#f0fff4', border: '1px solid #c8e6c9', borderRadius: 8,
          padding: '10px 14px', fontSize: 13, color: '#2e7d32', marginBottom: 20, textAlign: 'center',
        }}>
          Pla Free inclou 10 consultes/dia sense targeta
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#444', display: 'block', marginBottom: 6 }}>
              Email
            </label>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              required placeholder="correu@exemple.com"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#444', display: 'block', marginBottom: 6 }}>
              Contrasenya
            </label>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              required placeholder="Mínim 8 caràcters"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#444', display: 'block', marginBottom: 6 }}>
              Confirma la contrasenya
            </label>
            <input
              type="password" value={password2} onChange={e => setPassword2(e.target.value)}
              required placeholder="••••••••"
              style={inputStyle}
            />
          </div>

          {error && (
            <div style={{ background: '#fff0f0', border: '1px solid #ffcdd2', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#c62828' }}>
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={btnStyle}>
            {loading ? 'Creant compte...' : 'Crear compte gratis'}
          </button>
        </form>

        <p style={{ textAlign: 'center', fontSize: 13, color: '#999', marginTop: 24 }}>
          Ja tens compte?{' '}
          <Link to="/login" style={{ color: '#0f3460', fontWeight: 700, textDecoration: 'none' }}>
            Inicia sessió
          </Link>
        </p>
        <p style={{ textAlign: 'center', fontSize: 13, color: '#999', marginTop: 8 }}>
          <Link to="/" style={{ color: '#999', textDecoration: 'none' }}>← Tornar a l'inici</Link>
        </p>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 14px', borderRadius: 8,
  border: '1.5px solid #e0e0e0', fontSize: 14, outline: 'none',
  boxSizing: 'border-box',
}

const btnStyle: React.CSSProperties = {
  background: '#e8b84b', color: '#1a1a2e', border: 'none',
  padding: '12px 0', borderRadius: 8, fontSize: 15, fontWeight: 700,
  cursor: 'pointer', marginTop: 4,
}
