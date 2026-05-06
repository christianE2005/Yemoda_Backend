import { useState, useEffect } from 'react';
import { Github, Shield, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { githubService } from '../../services/github.service';
import { useAuth } from '../context/AuthContext';

const ORG_OWNER = 'ABCDH-Technologies';

/**
 * Reusable GitHub connection section.
 * Shows "Connect" button when not connected, or a connected badge otherwise.
 * Handles the OAuth callback (code/state query params) transparently.
 */
export function GitHubConnectSection() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const isStakeholder = user?.role === 'stakeholder';

  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [githubLogin, setGithubLogin] = useState<string | null>(null);
  const [isAdmin] = useState(() => githubService.isAdmin());

  useEffect(() => {
    if (!userId) { setLoading(false); return; }

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    // Handle OAuth callback redirect
    if (params.get('github') === 'connected' && code && state) {
      window.history.replaceState({}, '', window.location.pathname);
      setBusy(true);

      githubService.completeOAuth({ code, state })
        .then((res) => {
          setGithubLogin(res.github_login);
          setConnected(true);
          toast.success('Cuenta de GitHub conectada', {
            description: `Conectado como ${res.github_login} en ${ORG_OWNER}`,
          });
        })
        .catch((err) => {
          const detail = err instanceof Error ? err.message : 'Error desconocido';
          toast.error('Error al completar la conexion con GitHub', { description: detail });
        })
        .finally(() => { setBusy(false); setLoading(false); });
      return;
    }

    if (params.get('github') === 'connected') {
      window.history.replaceState({}, '', window.location.pathname);
      toast.error('Falto el codigo de autorizacion. Intenta de nuevo.');
    }

    // Check connection status with backend
    githubService.checkConnectionStatus()
      .then((status) => {
        if (status.connected) {
          setConnected(true);
          setGithubLogin(status.github_login);
        } else if (status.reason === 'token_expired') {
          toast.info('Tu conexion con GitHub expiro. Vuelve a conectar.');
        }
      })
      .catch(() => { /* endpoint may not exist yet */ })
      .finally(() => setLoading(false));
  }, [userId]);

  const handleConnect = async () => {
    setBusy(true);
    try {
      await githubService.startOAuth();
    } catch {
      toast.error('No se pudo iniciar la conexion con GitHub');
      setBusy(false);
    }
  };

  const handleInstallApp = async () => {
    setBusy(true);
    try {
      await githubService.startAppInstall();
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Error desconocido';
      toast.error('No se pudo iniciar la instalacion', { description: detail });
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('¿Estás seguro de que deseas desconectar tu cuenta de GitHub?')) {
      return;
    }
    setBusy(true);
    try {
      await githubService.disconnectGitHub();
      toast.success('Desconectado exitosamente', {
        description: 'Tu cuenta de GitHub ha sido desconectada',
      });
      setTimeout(() => window.location.reload(), 500);
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Error desconocido';
      toast.error('No se pudo desconectar', { description: detail });
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3">
        <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-[11px] text-muted-foreground">Verificando GitHub...</span>
      </div>
    );
  }

  if (isStakeholder) {
    return (
      <div className="rounded-[4px] border border-border bg-surface-secondary/30 px-3 py-3">
        <p className="text-[12px] font-medium text-foreground">GitHub no disponible para Stakeholders</p>
        <p className="text-[10px] text-muted-foreground mt-1">
          Este rol solo tiene acceso de consulta dentro de la plataforma y no puede conectar una cuenta de GitHub.
        </p>
      </div>
    );
  }

  if (connected) {
    return (
      <div className="flex items-center gap-3 py-2 px-3 border border-border rounded-[4px] bg-accent/20">
        <div className="w-8 h-8 bg-[#24292e] rounded-full flex items-center justify-center">
          <Github className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
            <span className="text-[12px] font-medium text-foreground">Ya estas conectado con GitHub</span>
          </div>
          {githubLogin && (
            <p className="text-[10px] text-muted-foreground mt-0.5">
              <span className="font-mono text-foreground">{githubLogin}</span>
              {' · '}
              <span className="font-mono text-foreground">{ORG_OWNER}</span>
            </p>
          )}
        </div>
        <button
          onClick={handleDisconnect}
          disabled={busy}
          className="px-3 py-1.5 bg-destructive/10 text-destructive hover:bg-destructive/20 rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed whitespace-nowrap"
        >
          {busy ? 'Desconectando...' : 'Desconectar'}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 py-2 px-3 border border-border rounded-[4px]">
        <div className="w-8 h-8 bg-muted rounded-full flex items-center justify-center">
          <Github className="w-4 h-4 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-medium text-foreground">GitHub no conectado</p>
          <p className="text-[10px] text-muted-foreground">
            Vincula tu cuenta para gestionar repositorios en{' '}
            <span className="font-mono text-foreground">{ORG_OWNER}</span>
          </p>
        </div>
        <button
          onClick={handleConnect}
          disabled={busy}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#24292e] hover:bg-[#1b1f23] text-white rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-60"
        >
          <Github className="w-3.5 h-3.5" />
          {busy ? 'Redirigiendo...' : 'Iniciar sesion con GitHub'}
        </button>
      </div>

      {isAdmin && (
        <button
          onClick={handleInstallApp}
          disabled={busy}
          className="flex items-center gap-2 px-3 py-1.5 border border-border hover:bg-accent/30 text-foreground rounded-[4px] text-[11px] font-medium transition-colors disabled:opacity-60"
        >
          <Shield className="w-3.5 h-3.5" />
          Instalar App en organizacion
        </button>
      )}
    </div>
  );
}
