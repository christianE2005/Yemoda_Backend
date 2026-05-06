import { useState, useEffect, useCallback } from 'react';
import { projectsService, tasksService, usersService, githubService, ApiRequestError } from '../../services';
import type {
  ApiProject, ApiTask, ApiUserAccount, ApiTaskStatus, ApiTaskPriority,
  ApiBoard, ApiProjectMember, ApiActivityLog, ApiRole, ApiTaskWarning, ApiGithubPushEvent, ApiTaskAssignment,
  ApiBoardColumn, ApiSprint, ApiMilestone, ApiTag,
} from '../../services';

// â”€â”€â”€ Real API hooks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetches the real project list from Django backend.
 * Falls back to null on network / auth errors so the UI can degrade gracefully.
 */
export function useApiProjects(): UseApiState<ApiProject[]> {
  const [data, setData]       = useState<ApiProject[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    projectsService.list()
      .then((projects) => { if (!cancelled) setData(projects); })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiRequestError) {
          setError(err.message);
        } else {
          setError('No se pudo conectar al servidor.');
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

export interface UseApiTasksState extends UseApiState<ApiTask[]> {
  statuses: ApiTaskStatus[];
  priorities: ApiTaskPriority[];
}

/**
 * Fetches tasks filtered by board and/or project, with status/priority lookup tables.
 */
export function useApiTasks(boardId?: number, projectId?: number): UseApiTasksState {
  const [data, setData]           = useState<ApiTask[] | null>(null);
  const [statuses, setStatuses]   = useState<ApiTaskStatus[]>([]);
  const [priorities, setPriorities] = useState<ApiTaskPriority[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [tick, setTick]           = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      tasksService.list(boardId, projectId),
      tasksService.listStatuses().catch(() => []),
      tasksService.listPriorities().catch(() => []),
    ])
      .then(([tasks, sts, prios]) => {
        if (cancelled) return;
        setData(tasks);
        setStatuses(sts);
        setPriorities(prios);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando tareas.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [boardId, projectId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch, statuses, priorities };
}

export interface UseApiUsersState extends UseApiState<ApiUserAccount[]> {}

/** Fetches all user accounts (admin/manager use). */
export function useApiUsers(): UseApiUsersState {
  const [data, setData]       = useState<ApiUserAccount[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    usersService.list()
      .then((users) => { if (!cancelled) setData(users); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando usuarios.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

// â”€â”€â”€ Additional API hooks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/** Fetches boards, optionally filtered by project. */
export function useApiBoards(projectId?: number): UseApiState<ApiBoard[]> {
  const [data, setData]       = useState<ApiBoard[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listBoards(projectId)
      .then((boards) => { if (!cancelled) setData(boards); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando boards.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [projectId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches board columns, optionally filtered by board. */
export function useApiBoardColumns(boardId?: number): UseApiState<ApiBoardColumn[]> {
  const [data, setData]       = useState<ApiBoardColumn[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listBoardColumns(boardId)
      .then((columns) => { if (!cancelled) setData(columns); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando columnas.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [boardId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches sprints, optionally filtered by project. */
export function useApiSprints(projectId?: number): UseApiState<ApiSprint[]> {
  const [data, setData]       = useState<ApiSprint[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listSprints(projectId)
      .then((sprints) => { if (!cancelled) setData(sprints); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando sprints.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [projectId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches milestones, optionally filtered by project. */
export function useApiMilestones(projectId?: number): UseApiState<ApiMilestone[]> {
  const [data, setData]       = useState<ApiMilestone[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listMilestones(projectId)
      .then((milestones) => { if (!cancelled) setData(milestones); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando milestones.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [projectId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches tags, optionally filtered by project. */
export function useApiTags(projectId?: number): UseApiState<ApiTag[]> {
  const [data, setData]       = useState<ApiTag[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listTags(projectId)
      .then((tags) => { if (!cancelled) setData(tags); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando tags.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [projectId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches project members, optionally filtered by project and/or user. */
export function useApiProjectMembers(projectId?: number, userId?: number): UseApiState<ApiProjectMember[]> {
  const [data, setData]       = useState<ApiProjectMember[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    usersService.listMembers(projectId, userId)
      .then((members) => {
        if (cancelled) return;
        // Some backends ignore the user filter; enforce it client-side.
        const filteredMembers = userId ? members.filter((m) => m.user === userId) : members;
        setData(filteredMembers);
      })
      .catch((err) => {
        // Some backends don't support filtering members by user query param.
        // Fallback: fetch by project only and filter client-side.
        if (!userId || cancelled) throw err;
        return usersService.listMembers(projectId)
          .then((members) => {
            if (!cancelled) setData(members.filter((m) => m.user === userId));
          });
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando miembros.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [projectId, userId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches activity logs. */
export function useApiActivityLogs(limit = 50): UseApiState<ApiActivityLog[]> {
  const [data, setData]       = useState<ApiActivityLog[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    usersService.listActivity(limit)
      .then((logs) => { if (!cancelled) setData(logs); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando logs.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [limit, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches all roles. */
export function useApiRoles(): UseApiState<ApiRole[]> {
  const [data, setData]       = useState<ApiRole[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    usersService.listRoles()
      .then((roles) => { if (!cancelled) setData(roles); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando roles.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches task warnings with optional filters. */
export function useApiTaskWarnings(filters?: { task_id?: number; project_id?: number; status?: 'active' | 'resolved' }): UseApiState<ApiTaskWarning[]> {
  const [data, setData]       = useState<ApiTaskWarning[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  const filterKey = JSON.stringify(filters ?? {});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listWarnings(filters)
      .then((warnings) => { if (!cancelled) setData(warnings); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando warnings.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches task assignments and optionally filters them to a known set of task ids client-side. */
export function useApiTaskAssignments(taskIds?: number[]): UseApiState<ApiTaskAssignment[]> {
  const [data, setData]       = useState<ApiTaskAssignment[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  const taskIdsKey = JSON.stringify(taskIds ?? []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    tasksService.listAssignments()
      .then((assignments) => {
        if (cancelled) return;
        const nextData = taskIds && taskIds.length > 0
          ? assignments.filter((assignment) => taskIds.includes(assignment.task))
          : assignments;
        setData(nextData);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando asignaciones.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [taskIdsKey, tick, taskIds]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}

/** Fetches GitHub push events with optional filters. */
export function useApiGithubPushes(filters?: { project_id?: number; repo?: string }): UseApiState<ApiGithubPushEvent[]> {
  const [data, setData]       = useState<ApiGithubPushEvent[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [tick, setTick]       = useState(0);

  const filterKey = JSON.stringify(filters ?? {});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    githubService.listPushes(filters)
      .then((pushes) => { if (!cancelled) setData(pushes); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : 'Error cargando pushes.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}
