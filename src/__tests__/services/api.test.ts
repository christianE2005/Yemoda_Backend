import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tokenStore, api, ApiRequestError, AUTH_SESSION_EXPIRED_EVENT } from '../../services/api';

// Mock localStorage
const storage = new Map<string, string>();
const localStorageMock = {
  getItem: vi.fn((key: string) => storage.get(key) ?? null),
  setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
  removeItem: vi.fn((key: string) => storage.delete(key)),
  clear: vi.fn(() => storage.clear()),
  get length() { return storage.size; },
  key: vi.fn(() => null),
};
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true });

// Mock fetch
const fetchMock = vi.fn();
globalThis.fetch = fetchMock;

beforeEach(() => {
  storage.clear();
  fetchMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('tokenStore', () => {
  it('stores and retrieves tokens', () => {
    tokenStore.set('access123', 'refresh456');
    expect(tokenStore.getAccess()).toBe('access123');
    expect(tokenStore.getRefresh()).toBe('refresh456');
  });

  it('clears tokens', () => {
    tokenStore.set('a', 'r');
    tokenStore.clear();
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
  });

  it('setAccess updates only the access token', () => {
    tokenStore.set('old_access', 'old_refresh');
    tokenStore.setAccess('new_access');
    expect(tokenStore.getAccess()).toBe('new_access');
    expect(tokenStore.getRefresh()).toBe('old_refresh');
  });
});

describe('api.get', () => {
  it('makes GET request with auth header', async () => {
    tokenStore.set('mytoken', 'myrefresh');
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([{ id: 1, name: 'Test' }]),
    });

    const result = await api.get('/projects/');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/projects/');
    expect(options.headers['Authorization']).toBe('Bearer mytoken');
    expect(options.method).toBe('GET');
    expect(result).toEqual([{ id: 1, name: 'Test' }]);
  });

  it('throws ApiRequestError on non-ok response', async () => {
    tokenStore.clear();
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'Not found' }),
    });

    try {
      await api.get('/projects/999/', false);
      expect.fail('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiRequestError);
      expect((err as ApiRequestError).status).toBe(404);
    }
  });

  it('handles 204 No Content', async () => {
    tokenStore.clear();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: () => Promise.reject(new Error('no body')),
    });

    const result = await api.delete('/tasks/1/', false);
    expect(result).toBeUndefined();
  });
});

describe('api.post', () => {
  it('sends JSON body', async () => {
    tokenStore.set('tok', 'ref');
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: () => Promise.resolve({ id_task: 1, title: 'New Task' }),
    });

    const result = await api.post('/tasks/', { board: 1, title: 'New Task' });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ board: 1, title: 'New Task' });
    expect(result).toEqual({ id_task: 1, title: 'New Task' });
  });
});

describe('401 retry with token refresh', () => {
  it('retries after successful refresh', async () => {
    tokenStore.set('expired_token', 'valid_refresh');

    // First call returns 401
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Token expired' }),
    });

    // Refresh call succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: 'new_token' }),
    });

    // Retry call succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([{ id: 1 }]),
    });

    const result = await api.get('/tasks/');
    expect(result).toEqual([{ id: 1 }]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(tokenStore.getAccess()).toBe('new_token');
  });

  it('clears tokens when refresh fails', async () => {
    const sessionExpiredListener = vi.fn();
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpiredListener);

    tokenStore.set('expired_token', 'invalid_refresh');

    // First call returns 401
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Token expired' }),
    });

    // Refresh call fails
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Invalid refresh token' }),
    });

    await expect(api.get('/tasks/')).rejects.toThrow(ApiRequestError);
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
    expect(sessionExpiredListener).toHaveBeenCalledTimes(1);

    window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpiredListener);
  });

  it('emits session-expired for auth requests when backend returns token-expired in non-401 response', async () => {
    const sessionExpiredListener = vi.fn();
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpiredListener);
    tokenStore.set('any_access', 'any_refresh');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Token expirado' }),
    });

    await expect(api.get('/projects/')).rejects.toThrow(ApiRequestError);
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
    expect(sessionExpiredListener).toHaveBeenCalledTimes(1);

    window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpiredListener);
  });

  it('does not emit session-expired for public unauthenticated requests', async () => {
    const sessionExpiredListener = vi.fn();
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpiredListener);

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Invalid credentials' }),
    });

    await expect(api.post('/auth/login/', { email: 'x', password: 'y' }, false)).rejects.toThrow(ApiRequestError);
    expect(sessionExpiredListener).toHaveBeenCalledTimes(0);

    window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpiredListener);
  });
});
