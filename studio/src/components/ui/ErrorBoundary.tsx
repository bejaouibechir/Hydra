/**
 * ErrorBoundary — filet de sécurité global de Hydra Studio.
 *
 * Toute exception de rendu non gérée (données corrompues, YAML invalide,
 * layout inattendu…) affiche un écran d'erreur récupérable au lieu d'une
 * page blanche. La boundary se réinitialise à chaque changement de route.
 */
import { Component, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { AlertTriangle, RotateCcw, Home } from 'lucide-react'

class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error('[Hydra Studio] Erreur de rendu interceptée :', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', minHeight: '60vh', gap: 14, padding: 24,
      }}>
        <AlertTriangle size={44} style={{ color: 'var(--error)' }} />
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
          Une erreur est survenue dans cette vue
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 520, textAlign: 'center' }}>
          Vos fichiers projet n'ont pas été modifiés. Si le problème persiste,
          un fichier du projet est peut-être invalide — vérifiez les YAML
          du workflow et des jobs concernés.
        </div>
        <pre style={{
          fontSize: 11, fontFamily: 'monospace', color: 'var(--error)',
          background: 'var(--bg-card)', border: '1px solid var(--bg-border)',
          borderRadius: 8, padding: '10px 14px', maxWidth: 640, maxHeight: 120,
          overflow: 'auto', whiteSpace: 'pre-wrap',
        }}>
          {String(this.state.error?.message ?? this.state.error)}
        </pre>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" onClick={() => this.setState({ error: null })}>
            <RotateCcw size={14} /> Réessayer
          </button>
          <a href="/overview" className="btn-secondary" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Home size={14} /> Retour à l'accueil
          </a>
        </div>
      </div>
    )
  }
}

/** Boundary réinitialisée à chaque navigation (clé = pathname) */
export default function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation()
  return <Boundary key={location.pathname}>{children}</Boundary>
}
