import type { ApiError } from './types';

// ─── Base URL ──────────────────────────────────────────────────────────────
const BASE_URL = import.meta.env.VITE_API_TARGET;

// ─── Token storage keys ──────────────────────────────────────────────────────
const STORAGE_ACCESS = 'pip_access_token';
const STORAGE_REFRESH = 'pip_refresh_token';
export const AUTH_SESSION_EXPIRED_EVENT = 'pip:auth-session-expired';

function emitSessionExpired() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(AUTH_SESSION_EXPIRED_EVENT));
}

function isSessionExpiredError(status: number, body: ApiError): boolean {
  if (status === 401) return true;

  const detail = String(body?.detail ?? '').toLowerCase();
  return (status === 403 || status === 400)
    && detail.includes('token')
    && (detail.includes('expir') || detail.includes('venc'));
}

export const tokenStore = {
  getAccess: () => localStorage.getItem(STORAGE_ACCESS),
  getRefresh: () => localStorage.getItem(STORAGE_REFRESH),
  set: (access: string, refresh: string) => {
    localStorage.setItem(STORAGE_ACCESS, access);
    localStorage.setItem(STORAGE_REFRESH, refresh);
  },
  setAccess: (access: string) => localStorage.setItem(STORAGE_ACCESS, access),
  clear: () => {
    localStorage.removeItem(STORAGE_ACCESS);
    localStorage.removeItem(STORAGE_REFRESH);
  },
};

// ─── API error class ─────────────────────────────────────────────────────────
export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public body: ApiError,
  ) {
    const message = body.detail ?? `HTTP ${status}`;
    super(message);
    this.name = 'ApiRequestError';
  }
}

// ─── Internal fetch helper ───────────────────────────────────────────────────
async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };

  if (auth) {
    const token = tokenStore.getAccess();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  const fullUrl = `${BASE_URL}${path}`;
  console.log(`[API] ${options.method || 'GET'} ${fullUrl}`);

  const res = await fetch(fullUrl, { ...options, headers });

  // 401 → try refresh once, then re-attempt
  if (res.status === 401 && auth) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${tokenStore.getAccess()}`;
      const retry = await fetch(`${BASE_URL}${path}`, { ...options, headers });
      return handleResponse<T>(retry, auth);
    }
    // Refresh failed — clear tokens and bubble up
    return handleResponse<T>(res, auth);
  }

  return handleResponse<T>(res, auth);
}

async function handleResponse<T>(res: Response, authRequest = true): Promise<T> {
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (authRequest && isSessionExpiredError(res.status, data as ApiError)) {
      tokenStore.clear();
      emitSessionExpired();
    }
    console.error(`[API] Error ${res.status} from ${res.url}:`, data);
    throw new ApiRequestError(res.status, data as ApiError);
  }
  return data as T;
}

async function tryRefresh(): Promise<boolean> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return false;
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    tokenStore.setAccess(data.access_token);
    return true;
  } catch {
    return false;
  }
}

// ─── Public API client ───────────────────────────────────────────────────────
export const api = {
  get: <T>(path: string, auth = true) =>
    request<T>(path, { method: 'GET' }, auth),

  post: <T>(path: string, body: unknown, auth = true) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }, auth),

  put: <T>(path: string, body: unknown, auth = true) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }, auth),

  patch: <T>(path: string, body: unknown, auth = true) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }, auth),

  delete: <T>(path: string, auth = true) =>
    request<T>(path, { method: 'DELETE' }, auth),
};
