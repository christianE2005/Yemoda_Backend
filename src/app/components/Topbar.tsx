import { Search, LogOut, Moon, Sun, ChevronDown } from 'lucide-react';
import { Link, useLocation, useParams, useNavigate } from 'react-router';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useState, useCallback, useRef, useEffect } from 'react';
import { toast } from 'sonner';
import { Tooltip, TooltipTrigger, TooltipContent } from './ui/tooltip';
import { NotificationBell } from './NotificationBell';
import { projectsService } from '../../services';

/* ── Breadcrumb route labels ── */
const routeLabels: Record<string, string> = {
  dashboard: 'Dashboard',
  projects: 'Proyectos',
  backlog: 'Backlog',
  profile: 'Perfil',
  settings: 'Configuración',
  logs: 'Logs',
  reports: 'Reportes',
  alerts: 'Alertas',
  users: 'Crear Usuarios',
};

export function Topbar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const [projectName, setProjectName] = useState<string | null>(null);

  const handleLogout = () => {
    logout();
    toast.success('Sesión cerrada');
    navigate('/login');
  };

  const openCommandPalette = useCallback(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }));
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    };
    if (showUserMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showUserMenu]);

  // Resolve project name for breadcrumb
  useEffect(() => {
    if (params.id && segments[0] === 'projects') {
      const pid = Number(params.id);
      if (pid) {
        projectsService.get(pid)
          .then((p) => setProjectName(p.name))
          .catch(() => setProjectName(null));
      }
    } else {
      setProjectName(null);
    }
  }, [params.id]);

  /* ── Breadcrumbs ── */
  const segments = location.pathname.split('/').filter(Boolean);
  const crumbs: { label: string; path?: string }[] = [];
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    const path = '/' + segments.slice(0, i + 1).join('/');
    const isLast = i === segments.length - 1;
    if (i === 1 && segments[0] === 'projects' && params.id) {
      crumbs.push({ label: projectName ?? `Proyecto #${params.id}`, path: isLast ? undefined : path });
    } else {
      crumbs.push({ label: routeLabels[segment] || segment, path: isLast ? undefined : path });
    }
  }

  return (
    <header className="bg-card border-b border-border h-[var(--topbar-height)] flex items-center justify-between px-4 shrink-0">
      {/* Left: Breadcrumbs + Search */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {/* Inline breadcrumbs */}
        {crumbs.length > 0 && (
          <nav className="flex items-center gap-1 text-[12px] shrink-0" aria-label="Breadcrumb">
            {crumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground/50">/</span>}
                {crumb.path ? (
                  <Link to={crumb.path} className="text-muted-foreground hover:text-foreground transition-colors">
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-foreground font-medium">{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
        )}

        {/* Separator */}
        {crumbs.length > 0 && <div className="h-4 w-px bg-border shrink-0" />}

        {/* Search trigger */}
        <button
          onClick={openCommandPalette}
          aria-label="Buscar (Ctrl+K)"
          className="flex items-center gap-2 pl-2 pr-2 py-1 bg-background rounded-[3px] border border-input text-[12px] text-muted-foreground hover:border-foreground/20 transition-colors cursor-pointer w-48 shrink-0"
        >
          <Search className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1 text-left truncate">Buscar...</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded-[2px] border border-border bg-muted px-1 py-0.5 text-[10px] font-medium text-muted-foreground shrink-0">
            Ctrl K
          </kbd>
        </button>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-0.5">
        {/* Notification Bell */}
        <NotificationBell />

        {/* Theme Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
              className="p-1.5 rounded-[3px] hover:bg-accent transition-colors"
            >
              {theme === 'dark' ? (
                <Sun className="w-4 h-4 text-muted-foreground" />
              ) : (
                <Moon className="w-4 h-4 text-muted-foreground" />
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent className="text-xs">{theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}</TooltipContent>
        </Tooltip>

        {/* Separator */}
        <div className="h-5 w-px bg-border mx-1" />

        {/* User Menu */}
        {user && (
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="flex items-center gap-1.5 pl-1.5 pr-1 py-1 rounded-[3px] hover:bg-accent transition-colors"
              aria-label="Menú de usuario"
              aria-expanded={showUserMenu}
            >
              <div className="w-6 h-6 rounded-full bg-primary/90 flex items-center justify-center shrink-0">
                <span className="text-[10px] font-semibold text-white">
                  {user.name.charAt(0).toUpperCase()}
                </span>
              </div>
              <span className="hidden md:block text-[12px] font-medium text-foreground max-w-[80px] truncate">
                {user.name.split(' ')[0]}
              </span>
              <ChevronDown className="w-3 h-3 text-muted-foreground" />
            </button>

            {showUserMenu && (
              <div className="absolute right-0 top-full mt-1 w-48 bg-card border border-border rounded-[4px] shadow-lg z-50 overflow-hidden">
                <div className="px-3 py-2.5 border-b border-border">
                  <p className="text-[12px] font-semibold text-foreground truncate">{user.name}</p>
                  <p className="text-[11px] text-muted-foreground capitalize truncate">{user.role.replace('_', ' ')}</p>
                </div>
                <button
                  onClick={() => { setShowUserMenu(false); navigate('/profile'); }}
                  className="w-full text-left px-3 py-2 text-[12px] text-foreground hover:bg-accent transition-colors"
                >
                  Ver perfil
                </button>
                {user.role !== 'admin' && (
                  <button
                    onClick={() => { setShowUserMenu(false); navigate('/settings'); }}
                    className="w-full text-left px-3 py-2 text-[12px] text-foreground hover:bg-accent transition-colors border-t border-border"
                  >
                    Configuración
                  </button>
                )}
                <button
                  onClick={() => { setShowUserMenu(false); handleLogout(); }}
                  className="w-full text-left px-3 py-2 text-[12px] text-destructive hover:bg-accent transition-colors border-t border-border flex items-center gap-2"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Cerrar sesión
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

