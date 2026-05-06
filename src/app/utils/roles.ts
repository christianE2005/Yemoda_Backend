export type UserRole = 'admin' | 'user' | 'stakeholder' | 'project_manager';

export const SYSTEM_ROLE_LABELS: Record<number, string> = {
  1: 'Admin',
  2: 'User',
  3: 'Stakeholder',
  4: 'Project Manager',
};

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Admin',
  user: 'User',
  stakeholder: 'Stakeholder',
  project_manager: 'Project Manager',
};

export const USER_ROLE_TO_SYSTEM_ROLE: Record<UserRole, number> = {
  admin: 1,
  user: 2,
  stakeholder: 3,
  project_manager: 4,
};

const SYSTEM_ROLE_TO_USER_ROLE: Record<number, UserRole> = {
  1: 'admin',
  2: 'user',
  3: 'stakeholder',
  4: 'project_manager',
};

const ROLE_NAME_MAP: Record<string, UserRole> = {
  admin: 'admin',
  administrador: 'admin',
  user: 'user',
  usuario: 'user',
  stakeholder: 'stakeholder',
  project_manager: 'project_manager',
  'project manager': 'project_manager',
  manager: 'project_manager',
  pm: 'project_manager',
  operative: 'stakeholder',
  operativo: 'stakeholder',
  executive: 'stakeholder',
  ejecutivo: 'stakeholder',
};

export function mapUserRole(systemRoleId?: number | null, roleName?: string | null): UserRole {
  if (systemRoleId && SYSTEM_ROLE_TO_USER_ROLE[systemRoleId]) {
    return SYSTEM_ROLE_TO_USER_ROLE[systemRoleId];
  }

  if (roleName) {
    return ROLE_NAME_MAP[roleName.trim().toLowerCase()] ?? 'stakeholder';
  }

  return 'stakeholder';
}

export function getSystemRoleLabel(systemRoleId: number, fallbackName?: string | null): string {
  return SYSTEM_ROLE_LABELS[systemRoleId] ?? fallbackName ?? `Rol #${systemRoleId}`;
}

export function getUserRoleLabel(role: UserRole): string {
  return USER_ROLE_LABELS[role];
}

export const SYSTEM_ROLE_OPTIONS = [
  { id: 1, label: 'Admin', role: 'admin' as UserRole },
  { id: 2, label: 'User', role: 'user' as UserRole },
  { id: 3, label: 'Stakeholder', role: 'stakeholder' as UserRole },
  { id: 4, label: 'Project Manager', role: 'project_manager' as UserRole },
];