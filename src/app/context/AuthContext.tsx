import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Clock3, LogOut } from 'lucide-react';
import { authService, tokenStore, usersService, AUTH_SESSION_EXPIRED_EVENT } from '../../services';
import type { ApiUserAccount } from '../../services';
import { mapUserRole } from '../utils/roles';
import type { UserRole } from '../utils/roles';

export type { UserRole } from '../utils/roles';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
}

function apiUserToUser(apiUser: ApiUserAccount, roleOverride?: UserRole): User {
  const role = roleOverride ?? mapUserRole(apiUser.system_role, apiUser.system_role_name);
  return {
    id: String(apiUser.id_user),
    name: apiUser.username,
    email: apiUser.email,
    role,
  };
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, role?: UserRole) => Promise<void>;
  register: (name: string, email: string, password: string, systemRoleId?: number) => Promise<void>;
  logout: () => void;
  syncUser: (apiUser: ApiUserAccount) => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [redirectCountdown, setRedirectCountdown] = useState(5);

  const persistUser = (nextUser: User | null) => {
    setUser(nextUser);
    if (nextUser) {
      localStorage.setItem('pip_user', JSON.stringify(nextUser));
      return;
    }

    localStorage.removeItem('pip_user');
  };

  // On mount: if token exists, restore the user from localStorage
  useEffect(() => {
    const stored = localStorage.getItem('pip_user');
    if (stored && tokenStore.getAccess()) {
      try {
        setUser(JSON.parse(stored) as User);
      } catch {
        // corrupted — clear
        tokenStore.clear();
        localStorage.removeItem('pip_user');
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!sessionExpired) return;

    setRedirectCountdown(5);

    const intervalId = window.setInterval(() => {
      setRedirectCountdown((current) => {
        if (current <= 1) {
          window.clearInterval(intervalId);
          window.location.href = '/';
          return 0;
        }
        return current - 1;
      });
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [sessionExpired]);

  useEffect(() => {
    const handleSessionExpired = () => {
      authService.logout();
      persistUser(null);
      setSessionExpired(true);
    };

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const login = async (email: string, password: string, role?: UserRole) => {
    try {
      const data = await authService.login(email, password);
      const u = apiUserToUser(data.user, role);
      setSessionExpired(false);
      persistUser(u);
    } catch (err) {
      // Always return generic message for security
      throw new Error('Correo o contraseña incorrectos.');
    }
  };

  const register = async (name: string, email: string, password: string, systemRoleId?: number) => {
    try {
      const apiUser = await authService.register(email, name, password);
      // Auto-login after register
      await login(email, password);
      // Assign system role if provided
      if (systemRoleId) {
        await usersService.update(apiUser.id_user, { system_role: systemRoleId });
      }
    } catch (err) {
      // Always return generic message for security
      throw new Error('No se pudo completar el registro. Intenta más tarde.');
    }
  };

  const logout = () => {
    setSessionExpired(false);
    authService.logout();
    persistUser(null);
  };

  const syncUser = (apiUser: ApiUserAccount) => {
    persistUser(apiUserToUser(apiUser));
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, syncUser, isAuthenticated: !!user }}>
      {children}
      {sessionExpired && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-background/96 px-6">
          <div className="w-full max-w-md rounded-[10px] border border-border bg-card p-6 shadow-2xl">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-warning/15 text-warning">
              <LogOut className="h-5 w-5" />
            </div>
            <div className="text-center">
              <h2 className="text-[18px] font-semibold text-foreground">Tu sesión venció</h2>
              <p className="mt-2 text-[13px] leading-6 text-muted-foreground">
                Tu login expiró y ya no pudimos renovarlo. Te enviaremos a la pantalla principal para que vuelvas a iniciar sesión.
              </p>
            </div>

            <div className="mt-5 rounded-[8px] border border-border bg-surface-secondary/40 px-4 py-3">
              <div className="flex items-center justify-center gap-2 text-[12px] font-medium text-foreground">
                <Clock3 className="h-3.5 w-3.5 text-muted-foreground" />
                Redirigiendo en {redirectCountdown} segundo{redirectCountdown === 1 ? '' : 's'}
              </div>
            </div>

            <button
              type="button"
              onClick={() => { window.location.href = '/'; }}
              className="mt-4 h-10 w-full rounded-[6px] bg-primary text-[12px] font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              Ir ahora
            </button>
          </div>
        </div>
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

