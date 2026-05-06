import { api } from './api';
import type { ApiProject } from './types';

export interface CreateProjectPayload {
  name: string;
  description?: string;
  end_date?: string;   // YYYY-MM-DD
  status?: string;
}

export interface UpdateProjectPayload extends Partial<CreateProjectPayload> {}

export const projectsService = {
  /** GET /api/projects/ */
  list(): Promise<ApiProject[]> {
    return api.get<ApiProject[]>('/projects/');
  },

  /** GET /api/projects/:id/ */
  get(id: number): Promise<ApiProject> {
    return api.get<ApiProject>(`/projects/${id}/`);
  },

  /** POST /api/projects/ */
  create(payload: CreateProjectPayload): Promise<ApiProject> {
    return api.post<ApiProject>('/projects/', payload);
  },

  /** PATCH /api/projects/:id/ */
  update(id: number, payload: UpdateProjectPayload): Promise<ApiProject> {
    return api.patch<ApiProject>(`/projects/${id}/`, payload);
  },

  /** DELETE /api/projects/:id/ */
  delete(id: number): Promise<void> {
    return api.delete<void>(`/projects/${id}/`);
  },
};
