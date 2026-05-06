import type { ApiBoard, ApiProject, ApiTask } from '../../services/types';

export type ProjectHealth = 'green' | 'yellow' | 'red';

export interface ProjectProgress {
  completed: number;
  total: number;
  percentage: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;
const NEAR_DEADLINE_DAYS = 14;
const ELAPSED_THRESHOLD = 0.75;

export function computeProjectProgress(
  projectId: number,
  tasks: Array<Pick<ApiTask, 'board' | 'completed_at'>>,
  boards: Array<Pick<ApiBoard, 'id_board' | 'project'>>,
): ProjectProgress {
  const projectBoardIds = new Set(
    boards.filter((board) => board.project === projectId).map((board) => board.id_board),
  );

  let total = 0;
  let completed = 0;
  for (const task of tasks) {
    if (!projectBoardIds.has(task.board ?? 0)) continue;
    total += 1;
    if (task.completed_at) completed += 1;
  }

  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  return { completed, total, percentage };
}

export function getProjectHealth(
  project: Pick<ApiProject, 'created_at' | 'end_date' | 'status'>,
  progress: ProjectProgress,
  now: Date = new Date(),
): ProjectHealth {
  if (progress.total === 0) return 'yellow';

  const pct = progress.percentage;
  if (pct >= 100) return 'green';

  const nowTime = now.getTime();
  const endTime = project.end_date ? new Date(project.end_date).getTime() : null;
  const startTime = project.created_at ? new Date(project.created_at).getTime() : null;

  if (endTime !== null && endTime < nowTime) return 'red';

  if (pct < 40 && endTime !== null && startTime !== null) {
    const span = endTime - startTime;
    if (span > 0) {
      const elapsedRatio = (nowTime - startTime) / span;
      if (elapsedRatio >= ELAPSED_THRESHOLD) return 'red';
    }
  }

  if (endTime !== null) {
    const daysRemaining = (endTime - nowTime) / DAY_MS;
    if (daysRemaining < NEAR_DEADLINE_DAYS && pct < 75) return 'yellow';
  }

  if (pct >= 75) return 'green';
  return 'yellow';
}
