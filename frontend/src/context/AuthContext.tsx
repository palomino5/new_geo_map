import { createContext, useCallback, useContext, useEffect, useState } from 'react'

export interface AuthUser {
  id: number
  email: string
  plan: 'free' | 'starter' | 'professional' | 'enterprise'
}

interface AuthState {
  user: AuthUser | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const TOKEN_KEY = 'geomap_token'

async function apiAuth(path: string, body: object): Promise<{ access_token: string; user: AuthUser }> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'Error desconegut')
  return data
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))

  // Restaura sessió en carregar
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY)
    if (!saved) return
    fetch(`${BASE_URL}/auth/me`, { headers: { Authorization: `Bearer ${saved}` } })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((u: AuthUser) => { setUser(u); setToken(saved) })
      .catch(() => { localStorage.removeItem(TOKEN_KEY); setToken(null) })
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { access_token, user: u } = await apiAuth('/auth/login', { email, password })
    localStorage.setItem(TOKEN_KEY, access_token)
    setToken(access_token)
    setUser(u)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const { access_token, user: u } = await apiAuth('/auth/register', { email, password })
    localStorage.setItem(TOKEN_KEY, access_token)
    setToken(access_token)
    setUser(u)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
