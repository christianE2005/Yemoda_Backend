import { api, tokenStore } from './api';
import type { LoginResponse, RefreshResponse, RegisterResponse } from './types';

export const authService = {
  /**
   * POST /api/auth/login/
   * Stores tokens and returns the full response.
   */
  async login(email: string, password: string): Promise<LoginResponse> {
    const data = await api.post<LoginResponse>(
      '/auth/login/',
      { email, password },
      false, // no auth header needed for login
    );
    tokenStore.set(data.access_token, data.refresh_token);
    return data;
  },

  /**
   * POST /api/auth/register/
   */
  async register(email: string, username: string, password: string, role?: string): Promise<RegisterResponse> {
    return api.post<RegisterResponse>(
      '/auth/register/',
      { email, username, password, ...(role && { role }) },
      false,
    );
  },

  /**
   * POST /api/auth/refresh/
   */
  async refresh(refreshToken: string): Promise<RefreshResponse> {
    return api.post<RefreshResponse>(
      '/auth/refresh/',
      { refresh_token: refreshToken },
      false,
    );
  },

  /** Remove tokens from storage (client-side logout). */
  logout(): void {
    tokenStore.clear();
  },

  /** Returns true if an access token exists locally. */
  isAuthenticated(): boolean {
    return !!tokenStore.getAccess();
  },
};
