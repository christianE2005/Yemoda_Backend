import { api } from './api';
import type { ApiUserAccount, ApiProjectMember, ApiRole, ApiActivityLog, ApiSystemRole } from './types';

export const usersService = {
  /** GET /api/user-accounts/ */
  list(): Promise<ApiUserAccount[]> {
    return api.get<ApiUserAccount[]>('/user-accounts/');
  },

  /** GET /api/user-accounts/:id/ */
  get(id: number): Promise<ApiUserAccount> {
    return api.get<ApiUserAccount>(`/user-accounts/${id}/`);
  },

  /** POST /api/user-accounts/ — Create a new user (admin only) */
  create(payload: { username: string; email: string; password: string; system_role?: number }): Promise<ApiUserAccount> {
    return api.post<ApiUserAccount>('/user-accounts/', payload);
  },

  /** PATCH /api/user-accounts/:id/ */
  update(id: number, payload: Partial<Pick<ApiUserAccount, 'email' | 'username' | 'system_role'> & { password: string }>): Promise<ApiUserAccount> {
    return api.patch<ApiUserAccount>(`/user-accounts/${id}/`, payload);
  },

  /** DELETE /api/user-accounts/:id/ */
  delete(id: number): Promise<void> {
    return api.delete<void>(`/user-accounts/${id}/`);
  },

  /** GET /api/system-roles/ */
  listSystemRoles(): Promise<ApiSystemRole[]> {
    return api.get<ApiSystemRole[]>('/system-roles/');
  },

  // ── Project members ────────────────────────────────────────────
  listMembers(projectId?: number, userId?: number): Promise<ApiProjectMember[]> {
    const params = new URLSearchParams();
    if (projectId) params.set('project', String(projectId));
    if (userId) params.set('user', String(userId));
    const query = params.toString();
    const url = query ? `/project-members/?${query}` : '/project-members/';
    return api.get<ApiProjectMember[]>(url);
  },

  async addMember(projectId: number, userId: number, roleId?: number): Promise<ApiProjectMember> {
    try {
      return await api.post<ApiProjectMember>('/project-members/', {
        project: projectId,
        user: userId,
        role: roleId ?? null,
      });
    } catch {
      try {
        return await api.post<ApiProjectMember>('/project-members/', {
          project_id: projectId,
          user_id: userId,
          role_id: roleId ?? null,
        });
      } catch {
        return api.post<ApiProjectMember>(`/projects/${projectId}/members/`, {
          user_id: userId,
          role_id: roleId ?? null,
        });
      }
    }
  },

  updateMember(memberId: number, payload: Partial<Pick<ApiProjectMember, 'user' | 'project' | 'role'>>): Promise<ApiProjectMember> {
    return api.patch<ApiProjectMember>(`/project-members/${memberId}/`, payload);
  },

  removeMember(memberId: number): Promise<void> {
    return api.delete<void>(`/project-members/${memberId}/`);
  },

  // ── Roles ──────────────────────────────────────────────────────
  listRoles(): Promise<ApiRole[]> {
    return api.get<ApiRole[]>('/roles/');
  },

  // ── Activity log ───────────────────────────────────────────────
  listActivity(limit = 50): Promise<ApiActivityLog[]> {
    return api.get<ApiActivityLog[]>(`/activity-logs/?ordering=-created_at&limit=${limit}`);
  },
};
