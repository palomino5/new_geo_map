import { useNavigate } from 'react-router-dom'
import Navbar from '../components/Navbar'

const STATS = [
  { num: '1,2M', label: "Parcel·les rústiques a Catalunya" },
  { num: '47.540', label: "Camps actius identificats" },
  { num: '2.487', label: "Camps abandonats detectats" },
  { num: '5 dies', label: "Freqüència d'actualització" },
]

const USE_CASES = [
  {
    icon: '🏡',
    title: 'Propietari agrícola',
    desc: 'Verifica si les teves finques arrendades s\'estan cultivant realment, sense visites físiques.',
  },
  {
    icon: '📋',
    title: 'Notari / Gestor',
    desc: 'Obté un informe objectiu de l\'estat d\'ús d\'una parcel·la per a transmissions patrimonials.',
  },
  {
    icon: '🏢',
    title: 'Asseguradora',
    desc: 'Substitueix inspeccions físiques per verificació automàtica basada en dades de satèl·lit.',
  },
  {
    icon: '📈',
    title: 'Inversor en terra',
    desc: 'Avalua el potencial productiu de qualsevol finca de Catalunya a distància i en temps real.',
  },
  {
    icon: '🏛️',
    title: 'Administració pública',
    desc: 'Dades per planificar polítiques d\'abandó agrícola i reactivació de zones rurals.',
  },
  {
    icon: '🔬',
    title: 'Investigador / Consultor',
    desc: 'Accés a historial NDVI per parcel·la i exportació massiva per estudis territorials.',
  },
]

const PLANS = [
  {
    name: 'Free',
    price: '0€',
    period: '/mes',
    features: ['Mapa interactiu', '10 consultes/dia', 'Estat actual', 'Sense historial'],
    cta: 'Comença ara',
    highlight: false,
  },
  {
    name: 'Starter',
    price: '9€',
    period: '/mes',
    features: ['Consultes il·limitades', 'Historial 1 any', 'Export 500 parc/mes', '5 informes PDF', '10 alertes'],
    cta: 'Prova 14 dies gratis',
    highlight: false,
  },
  {
    name: 'Professional',
    price: '49€',
    period: '/mes',
    features: ['Tot il·limitat', 'Historial 3 anys', 'API 10k req/mes', 'Export il·limitat', 'Suport prioritari'],
    cta: 'Prova 14 dies gratis',
    highlight: true,
  },
  {
    name: 'Enterprise',
    price: '299€',
    period: '/mes',
    features: ['API il·limitada', 'SLA garantit', 'Webhooks', 'Compte dedicat', 'Contracte anual'],
    cta: 'Contacta\'ns',
    highlight: false,
  },
]

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div style={{ fontFamily: "'Segoe UI', system-ui, sans-serif", color: '#1a1a2e', background: '#fff' }}>
      <Navbar />

      {/* Hero */}
      <section style={{
        background: 'linear-gradient(135deg, #0f3460 0%, #16213e 60%, #1a4a2e 100%)',
        color: 'white', padding: '80px 32px', textAlign: 'center',
      }}>
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          <div style={{
            display: 'inline-block', background: 'rgba(232,184,75,0.2)', color: '#e8b84b',
            padding: '4px 16px', borderRadius: 20, fontSize: 13, fontWeight: 600, marginBottom: 24,
          }}>
            Cobertura completa de Catalunya · Actualització setmanal
          </div>
          <h1 style={{ fontSize: 48, fontWeight: 800, lineHeight: 1.15, marginBottom: 20 }}>
            Sap si un camp<br />
            <span style={{ color: '#e8b84b' }}>està cultivat o abandonat</span>
          </h1>
          <p style={{ fontSize: 18, opacity: 0.85, lineHeight: 1.7, marginBottom: 36 }}>
            Creuem dades catastrals amb imatges de satèl·lit Sentinel-2 per classificar
            automàticament l'estat de cada parcel·la agrícola de Catalunya.
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/mapa')}
              style={{
                background: '#e8b84b', color: '#1a1a2e', border: 'none',
                padding: '14px 32px', borderRadius: 30, fontSize: 16, fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Explorar el mapa →
            </button>
            <button
              onClick={() => document.getElementById('preus')?.scrollIntoView({ behavior: 'smooth' })}
              style={{
                background: 'transparent', color: 'white',
                border: '2px solid rgba(255,255,255,0.4)',
                padding: '14px 32px', borderRadius: 30, fontSize: 16, fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Veure preus
            </button>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section style={{ background: '#f8f9fa', padding: '48px 32px' }}>
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24 }}>
          {STATS.map(s => (
            <div key={s.num} style={{ textAlign: 'center', padding: 24, background: 'white', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
              <div style={{ fontSize: 32, fontWeight: 800, color: '#0f3460' }}>{s.num}</div>
              <div style={{ fontSize: 13, color: '#666', marginTop: 6, lineHeight: 1.5 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Casos d'ús */}
      <section style={{ padding: '80px 32px' }}>
        <div style={{ maxWidth: 960, margin: '0 auto' }}>
          <h2 style={{ fontSize: 32, fontWeight: 800, textAlign: 'center', marginBottom: 12 }}>
            Per a qui és GeoMap?
          </h2>
          <p style={{ textAlign: 'center', color: '#666', fontSize: 16, marginBottom: 48 }}>
            Dades de satèl·lit per a decisions reals
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
            {USE_CASES.map(uc => (
              <div key={uc.title} style={{
                padding: 28, borderRadius: 12, border: '1px solid #e8e8e8',
                transition: 'box-shadow 0.2s',
              }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>{uc.icon}</div>
                <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>{uc.title}</h3>
                <p style={{ fontSize: 14, color: '#666', lineHeight: 1.6 }}>{uc.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Com funciona */}
      <section style={{ background: '#f8f9fa', padding: '80px 32px' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', textAlign: 'center' }}>
          <h2 style={{ fontSize: 32, fontWeight: 800, marginBottom: 12 }}>Com funciona?</h2>
          <p style={{ color: '#666', fontSize: 16, marginBottom: 48 }}>Tres passos, completament automàtics</p>
          <div style={{ display: 'flex', gap: 0, position: 'relative' }}>
            {[
              { num: '1', title: 'Dades catastrals', desc: 'Importem totes les parcel·les rústiques del Catastro INSPIRE' },
              { num: '2', title: 'Imatges Sentinel-2', desc: 'Descarreguem imatges de satèl·lit cada 5 dies amb <20% de núvols' },
              { num: '3', title: 'Classificació NDVI', desc: 'Calculem l\'índex de vegetació per parcel·la i classifiquem l\'estat' },
            ].map((step, i) => (
              <div key={step.num} style={{ flex: 1, padding: '0 16px', textAlign: 'center' }}>
                <div style={{
                  width: 56, height: 56, borderRadius: '50%', background: '#0f3460',
                  color: 'white', fontSize: 22, fontWeight: 800,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 16px',
                }}>
                  {step.num}
                </div>
                {i < 2 && (
                  <div style={{
                    position: 'absolute', top: 27, left: `${33 * (i + 1)}%`,
                    width: '16%', height: 2, background: '#0f3460', opacity: 0.3,
                  }} />
                )}
                <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>{step.title}</h3>
                <p style={{ fontSize: 13, color: '#666', lineHeight: 1.6 }}>{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Preus */}
      <section id="preus" style={{ padding: '80px 32px' }}>
        <div style={{ maxWidth: 960, margin: '0 auto' }}>
          <h2 style={{ fontSize: 32, fontWeight: 800, textAlign: 'center', marginBottom: 12 }}>Preus i plans</h2>
          <p style={{ textAlign: 'center', color: '#666', fontSize: 16, marginBottom: 48 }}>
            Comença gratis. Escala quan ho necessitis.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 20 }}>
            {PLANS.map(plan => (
              <div key={plan.name} style={{
                padding: 28, borderRadius: 14,
                background: plan.highlight ? '#0f3460' : 'white',
                color: plan.highlight ? 'white' : '#1a1a2e',
                border: plan.highlight ? 'none' : '1px solid #e8e8e8',
                boxShadow: plan.highlight ? '0 8px 32px rgba(15,52,96,0.3)' : '0 2px 8px rgba(0,0,0,0.06)',
                display: 'flex', flexDirection: 'column',
              }}>
                <div style={{ fontSize: 14, fontWeight: 700, opacity: plan.highlight ? 0.9 : 1, marginBottom: 8 }}>
                  {plan.name}
                </div>
                <div style={{ marginBottom: 20 }}>
                  <span style={{ fontSize: 36, fontWeight: 800 }}>{plan.price}</span>
                  <span style={{ fontSize: 14, opacity: 0.7 }}>{plan.period}</span>
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', flex: 1 }}>
                  {plan.features.map(f => (
                    <li key={f} style={{ fontSize: 13, padding: '5px 0', opacity: 0.85, display: 'flex', gap: 8 }}>
                      <span style={{ color: plan.highlight ? '#e8b84b' : '#4caf50' }}>✓</span> {f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => navigate('/mapa')}
                  style={{
                    padding: '10px 0', borderRadius: 8, fontWeight: 700, fontSize: 14,
                    cursor: 'pointer', border: 'none',
                    background: plan.highlight ? '#e8b84b' : '#f0f4ff',
                    color: plan.highlight ? '#1a1a2e' : '#0f3460',
                  }}
                >
                  {plan.cta}
                </button>
              </div>
            ))}
          </div>

          {/* Informe puntual */}
          <div style={{
            marginTop: 24, padding: '24px 32px', borderRadius: 12,
            background: '#f0fff4', border: '1px solid #4caf50',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>📋 Informe puntual — 9,90€</div>
              <div style={{ fontSize: 14, color: '#666', marginTop: 4 }}>
                Per a notaries i gestories. PDF amb historial 3 anys + estat actual. Sense subscripció.
              </div>
            </div>
            <button style={{
              background: '#4caf50', color: 'white', border: 'none',
              padding: '10px 24px', borderRadius: 8, fontWeight: 700, cursor: 'pointer',
            }}>
              Sol·licitar informe
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ background: '#0f3460', color: 'rgba(255,255,255,0.6)', padding: '40px 32px', textAlign: 'center', fontSize: 13 }}>
        <div style={{ marginBottom: 8, fontWeight: 700, color: 'white', fontSize: 15 }}>🌾 GeoMap Agrícola</div>
        <div>Dades catastrals + Sentinel-2 · Catalunya · {new Date().getFullYear()}</div>
      </footer>
    </div>
  )
}
