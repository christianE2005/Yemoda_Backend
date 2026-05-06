import type { ApiProjectMember, ApiRole, ApiUserAccount } from '../../services';

export interface ProjectRoleIds {
  projectManagerId: number | null;
  productOwnerId: number | null;
  scrumMasterId: number | null;
  developerId: number | null;
  stakeholderId: number | null;
}

export interface ProjectCapabilities {
  canAccessProject: boolean;
  canManageProject: boolean;
  canManageMembers: boolean;
  canEditMemberRoles: boolean;
  canManageTasks: boolean;
  canCreateRepos: boolean;
  isProjectManager: boolean;
  isProductOwner: boolean;
  isStakeholder: boolean;
}

export interface UserGithubConnectionState {
  connected: boolean | null;
  login: string | null;
}

const SYSTEM_STAKEHOLDER_ROLE_ID = 3;

function normalizeRoleName(value?: string | null) {
  return (value ?? '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function resolveRoleId(roles: ApiRole[], matchers: string[], fallbackId: number | null = null) {
  for (const role of roles) {
    const normalized = normalizeRoleName(role.name);
    if (matchers.some((matcher) => normalized === matcher || normalized.includes(matcher))) {
      return role.id_role;
    }
  }
  return fallbackId;
}

export function getProjectRoleIds(roles?: ApiRole[] | null): ProjectRoleIds {
  const safeRoles = roles ?? [];
  return {
    projectManagerId: resolveRoleId(safeRoles, ['project manager', 'pm'], 1),
    productOwnerId: resolveRoleId(safeRoles, ['product owner', 'po'], 2),
    scrumMasterId: resolveRoleId(safeRoles, ['scrum master', 'scrum'], 3),
    developerId: resolveRoleId(safeRoles, ['developer', 'dev'], 4),
    stakeholderId: resolveRoleId(safeRoles, ['stakeholder']),
  };
}

export function isStakeholderSystemUser(user?: ApiUserAccount | null) {
  return (user?.system_role ?? null) === SYSTEM_STAKEHOLDER_ROLE_ID;
}

export function getUserGithubConnectionState(user?: ApiUserAccount | null): UserGithubConnectionState {
  const login = user?.github_login ?? user?.github_username ?? null;
  if (typeof user?.github_connected === 'boolean') {
    return { connected: user.github_connected, login };
  }
  if (typeof user?.is_github_connected === 'boolean') {
    return { connected: user.is_github_connected, login };
  }
  if (login) {
    return { connected: true, login };
  }
  return { connected: null, login: null };
}

export function getAllowedProjectRoleIdsForUser(user: ApiUserAccount | null | undefined, roleIds: ProjectRoleIds) {
  if (isStakeholderSystemUser(user)) {
    return roleIds.stakeholderId != null ? [roleIds.stakeholderId] : [];
  }

  return [roleIds.productOwnerId, roleIds.scrumMasterId, roleIds.developerId].filter(
    (roleId): roleId is number => roleId != null,
  );
}

export function canEditMemberProjectRole(targetUser: ApiUserAccount | null | undefined, targetMember: ApiProjectMember | null | undefined, roleIds: ProjectRoleIds) {
  if (!targetMember) return false;
  if (targetMember.role != null && targetMember.role === roleIds.projectManagerId) return false;
  if (isStakeholderSystemUser(targetUser)) return false;
  return true;
}

export function getProjectCapabilities(
  currentUserMember: ApiProjectMember | null | undefined,
  currentUserAccount: ApiUserAccount | null | undefined,
  roleIds: ProjectRoleIds,
): ProjectCapabilities {
  const memberRoleId = currentUserMember?.role ?? null;
  const isProjectManager = memberRoleId != null && memberRoleId === roleIds.projectManagerId;
  const isProductOwner = memberRoleId != null && memberRoleId === roleIds.productOwnerId;
  const isStakeholder = isStakeholderSystemUser(currentUserAccount)
    || (roleIds.stakeholderId != null && memberRoleId === roleIds.stakeholderId);

  return {
    canAccessProject: Boolean(currentUserMember),
    canManageProject: isProjectManager,
    canManageMembers: isProjectManager,
    canEditMemberRoles: isProjectManager,
    canManageTasks: isProjectManager || isProductOwner,
    canCreateRepos: !isStakeholder,
    isProjectManager,
    isProductOwner,
    isStakeholder,
  };
}