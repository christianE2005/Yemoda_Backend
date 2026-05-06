import { api, tokenStore } from './api';
import type {
  GitHubAppInstallStartResponse,
  GitHubOAuthStartResponse,
  GitHubOAuthCallbackPayload,
  GitHubOAuthCallbackResponse,
  GitHubConnectionStatusResponse,
  GitHubCreateRepoPayload,
  GitHubCreateRepoResponse,
  GitHubRepo,
  ApiGithubPushEvent,
  ApiGithubCommitDiff,
} from './types';

// Per-user localStorage key for repos cache only
const reposKey = (uid: number | string) => `pip_gh_repos_${uid}`;

export const githubService = {
  // ─── Flow 3: Connection Status (always verify with backend) ────────────────

  /** GET /api/github/connection/status/ → check if user has active GitHub connection */
  async checkConnectionStatus(): Promise<GitHubConnectionStatusResponse> {
    return api.get<GitHubConnectionStatusResponse>('/github/connection/status/');
  },

  /** DELETE /api/github/connection/status/ → disconnect GitHub account */
  async disconnectGitHub(): Promise<void> {
    return api.delete('/github/connection/status/');
  },

  // ─── Flow 1: OAuth Connection ─────────────────────────────────────────────

  /** GET /api/github/app/oauth/start/ → redirect to GitHub OAuth */
  async startOAuth(): Promise<void> {
    const data = await api.get<GitHubOAuthStartResponse>('/github/app/oauth/start/');
    window.location.href = data.authorize_url;
  },

  /** POST /api/github/app/oauth/callback/ → exchange code for tokens + github_login */
  async completeOAuth(payload: GitHubOAuthCallbackPayload): Promise<GitHubOAuthCallbackResponse> {
    const res = await api.post<GitHubOAuthCallbackResponse>('/github/app/oauth/callback/', payload);
    // Backend returns new JWT tokens — persist them
    tokenStore.set(res.access_token, res.refresh_token);
    return res;
  },

  // ─── Flow 2: App Installation (Admin only) ────────────────────────────────

  /** GET /api/github/app/install/start/ → redirect to GitHub App installation page (admin only) */
  async startAppInstall(): Promise<void> {
    const data = await api.get<GitHubAppInstallStartResponse>('/github/app/install/start/');
    window.location.href = data.install_url;
  },

  // ─── Repos (cached per user in localStorage) ─────────────────────────────

  getRepos(userId: number | string): GitHubRepo[] {
    try {
      const raw = localStorage.getItem(reposKey(userId));
      return raw ? (JSON.parse(raw) as GitHubRepo[]) : [];
    } catch {
      return [];
    }
  },

  persistRepos(userId: number | string, repos: GitHubRepo[]): void {
    localStorage.setItem(reposKey(userId), JSON.stringify(repos));
  },

  clearRepos(userId: number | string): void {
    localStorage.removeItem(reposKey(userId));
  },

  // ─── Create Repo ───────────────────────────────────────────────────────────

  /** POST /api/github/repos/ → creates repository in the given org */
  async createRepo(payload: GitHubCreateRepoPayload): Promise<GitHubCreateRepoResponse> {
    return api.post<GitHubCreateRepoResponse>('/github/repos/', payload);
  },

  // ─── Push Events ───────────────────────────────────────────────────────────

  /** GET /api/github/pushes/ → list push events, optionally filtered */
  async listPushes(filters?: { project_id?: number; repo?: string }): Promise<ApiGithubPushEvent[]> {
    const params = new URLSearchParams();
    if (filters?.project_id) params.set('project_id', String(filters.project_id));
    if (filters?.repo) params.set('repo', filters.repo);
    const qs = params.toString();
    return api.get<ApiGithubPushEvent[]>(`/github/pushes/${qs ? `?${qs}` : ''}`);
  },

  /** GET /api/github/commits/diff/ → get diff for a specific commit */
  async getCommitDiff(repo: string, commitSha: string): Promise<ApiGithubCommitDiff> {
    return api.get<ApiGithubCommitDiff>(`/github/commits/diff/?repo=${encodeURIComponent(repo)}&commit=${encodeURIComponent(commitSha)}`);
  },

  /** GET /api/github/contents/ → browse repo file tree */
  async getContents(repo: string, path = '', ref?: string): Promise<unknown[]> {
    const params = new URLSearchParams({ repo });
    if (path) params.set('path', path);
    if (ref) params.set('ref', ref);
    return api.get<unknown[]>(`/github/contents/?${params.toString()}`);
  },

  /** GET /api/github/repos/ → list repos from backend, optionally filtered by project */
  async listRepos(filters?: { project_id?: number }): Promise<GitHubRepo[]> {
    const params = new URLSearchParams();
    if (filters?.project_id) params.set('project_id', String(filters.project_id));
    const qs = params.toString();
    return api.get<GitHubRepo[]>(`/github/repos/${qs ? `?${qs}` : ''}`);
  },

  // ─── Admin check (decode JWT without verification) ─────────────────────────

  isAdmin(): boolean {
    const token = tokenStore.getAccess();
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.is_admin === true;
    } catch {
      return false;
    }
  },
};
