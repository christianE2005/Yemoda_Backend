import type { CommandBarFilter } from '../components/CommandBar';

export type ProjectWorkflowStatus =
  | 'planning'
  | 'in_progress'
  | 'review'
  | 'completed'
  | 'retired'
  | 'cancelled';

type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'planning' | 'review' | 'retired' | 'cancelled';

interface ProjectStatusOption {
  value: ProjectWorkflowStatus;
  label: string;
  apiValue: string;
  badge: BadgeTone;
}

const PROJECT_STATUS_MAP: Record<ProjectWorkflowStatus, ProjectStatusOption> = {
  planning: { value: 'planning', label: 'Planeación', apiValue: 'Planeación', badge: 'planning' },
  in_progress: { value: 'in_progress', label: 'En Progreso', apiValue: 'En Progreso', badge: 'info' },
  review: { value: 'review', label: 'Revisión', apiValue: 'Revisión', badge: 'review' },
  completed: { value: 'completed', label: 'Finalizado', apiValue: 'Finalizado', badge: 'success' },
  retired: { value: 'retired', label: 'Retirado', apiValue: 'Retirado', badge: 'retired' },
  cancelled: { value: 'cancelled', label: 'Cancelado', apiValue: 'Cancelado', badge: 'cancelled' },
};

const PROJECT_STATUS_CHART_COLORS: Record<ProjectWorkflowStatus, string> = {
  planning: '#64748b',
  in_progress: '#0ea5e9',
  review: '#8b5cf6',
  completed: '#22c55e',
  retired: '#f97316',
  cancelled: '#ef4444',
};

const PROJECT_STATUS_ALIASES: Record<string, ProjectWorkflowStatus> = {
  planning: 'planning',
  planeacion: 'planning',
  'planeación': 'planning',
  planificacion: 'planning',
  'planificación': 'planning',
  in_progress: 'in_progress',
  'in progress': 'in_progress',
  progreso: 'in_progress',
  'en progreso': 'in_progress',
  active: 'in_progress',
  activo: 'in_progress',
  on_track: 'in_progress',
  review: 'review',
  revision: 'review',
  revisión: 'review',
  qa: 'review',
  testing: 'review',
  completed: 'completed',
  completado: 'completed',
  finalizado: 'completed',
  done: 'completed',
  retired: 'retired',
  retirado: 'retired',
  on_hold: 'retired',
  'on hold': 'retired',
  paused: 'retired',
  pausa: 'retired',
  'en pausa': 'retired',
  at_risk: 'retired',
  delayed: 'retired',
  cancelled: 'cancelled',
  cancelado: 'cancelled',
};

function normalizeProjectStatusKey(status?: string | null): string {
  return (status ?? '').trim().toLowerCase().replace(/[-\s]+/g, '_');
}

export function normalizeProjectStatus(status?: string | null): ProjectWorkflowStatus | null {
  if (!status) return null;
  const normalized = normalizeProjectStatusKey(status);
  return PROJECT_STATUS_ALIASES[normalized] ?? PROJECT_STATUS_ALIASES[normalized.replace(/_/g, ' ')] ?? null;
}

export function getProjectStatusOption(status?: string | null): ProjectStatusOption | null {
  const normalized = normalizeProjectStatus(status);
  return normalized ? PROJECT_STATUS_MAP[normalized] : null;
}

export function getProjectStatusLabel(status?: string | null): string {
  const option = getProjectStatusOption(status);
  if (option) return option.label;
  if (!status) return 'Sin estado';
  return status;
}

export function getProjectStatusApiValue(status?: string | null): string | null {
  const option = getProjectStatusOption(status);
  return option?.apiValue ?? null;
}

export function isTerminalProjectStatus(status?: string | null): boolean {
  const normalized = normalizeProjectStatus(status);
  return normalized === 'completed' || normalized === 'retired' || normalized === 'cancelled';
}

export function shouldShowInGenericProjectDisplays(status?: string | null): boolean {
  return !isTerminalProjectStatus(status);
}

function getProjectStatusPriority(status?: string | null): number {
  const normalized = normalizeProjectStatus(status);
  switch (normalized) {
    case 'in_progress':
      return 0;
    case 'review':
      return 1;
    case 'planning':
      return 2;
    case 'completed':
      return 3;
    case 'retired':
      return 4;
    case 'cancelled':
      return 5;
    default:
      return 6;
  }
}

export function compareProjectsForGenericPriority(
  left: { status?: string | null; end_date?: string | null; created_at?: string | null },
  right: { status?: string | null; end_date?: string | null; created_at?: string | null },
): number {
  const leftPriority = getProjectStatusPriority(left.status);
  const rightPriority = getProjectStatusPriority(right.status);

  if (leftPriority !== rightPriority) {
    return leftPriority - rightPriority;
  }

  const leftDue = left.end_date ? new Date(left.end_date).getTime() : Number.POSITIVE_INFINITY;
  const rightDue = right.end_date ? new Date(right.end_date).getTime() : Number.POSITIVE_INFINITY;

  if (leftDue !== rightDue) {
    return leftDue - rightDue;
  }

  const leftCreated = left.created_at ? new Date(left.created_at).getTime() : Number.POSITIVE_INFINITY;
  const rightCreated = right.created_at ? new Date(right.created_at).getTime() : Number.POSITIVE_INFINITY;
  return leftCreated - rightCreated;
}

export function getProjectStatusBadge(status?: string | null): BadgeTone {
  return getProjectStatusOption(status)?.badge ?? 'neutral';
}

export function getProjectStatusChartColor(status?: string | null): string {
  const normalized = normalizeProjectStatus(status);
  return normalized ? PROJECT_STATUS_CHART_COLORS[normalized] : '#94a3b8';
}

export const PROJECT_STATUS_OPTIONS: ProjectStatusOption[] = Object.values(PROJECT_STATUS_MAP);

export function buildProjectStatusFilters(statuses: Array<string | null | undefined>, current: string): CommandBarFilter[] {
  const uniqueStatuses = Array.from(new Set(statuses.map((status) => normalizeProjectStatus(status)).filter(Boolean))) as ProjectWorkflowStatus[];

  return uniqueStatuses.map((status) => ({
    label: PROJECT_STATUS_MAP[status].label,
    value: status,
    active: current === status,
    onClick: () => undefined,
  }));
}