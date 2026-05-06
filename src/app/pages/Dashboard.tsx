import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { motion } from 'motion/react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts';
import {
  Briefcase, ArrowRight, RefreshCw,
  CheckCircle2, Timer, ListChecks, AlertTriangle, Loader2,
} from 'lucide-react';
import { KPICard } from '../components/KPICard';
import { StatusBadge } from '../components/StatusBadge';
import { CommandBar } from '../components/CommandBar';
import { ProgressBar } from '../components/ProgressBar';
import { useApiBoards, useApiProjectMembers, useApiProjects, useApiTasks, useApiTaskAssignments, useApiTaskWarnings, useApiGithubPushes } from '../hooks/useProjectData';
import { useAuth } from '../context/AuthContext';
import { compareProjectsForGenericPriority, getProjectStatusBadge, getProjectStatusChartColor, getProjectStatusLabel, normalizeProjectStatus, shouldShowInGenericProjectDisplays } from '../utils/projectStatus';
import { formatProjectDate, getProjectDaysLabel } from '../utils/projectDates';
import { computeProjectProgress, getProjectHealth, type ProjectHealth } from '../utils/projectHealth';

const HEALTH_DOT_CLASS: Record<ProjectHealth, string> = {
  green: 'bg-success',
  yellow: 'bg-warning',
  red: 'bg-destructive',
};

const HEALTH_LABEL: Record<ProjectHealth, string> = {
  green: 'Saludable',
  yellow: 'En riesgo',
  red: 'Crítico',
};

const DASHBOARD_PANEL_BATCH_SIZE = 10;

function getTaskStatusChartColor(statusName: string) {
  const normalized = statusName.trim().toLowerCase();
  if (normalized.includes('backlog')) return '#64748b';
  if (normalized.includes('to do') || normalized.includes('por hacer')) return '#0ea5e9';
  if (normalized.includes('progress') || normalized.includes('progreso')) return '#f59e0b';
  if (normalized.includes('review') || normalized.includes('revision') || normalized.includes('revisión')) return '#8b5cf6';
  if (normalized.includes('done') || normalized.includes('completad') || normalized.includes('finalizad')) return '#22c55e';
  if (normalized.includes('block') || normalized.includes('bloque')) return '#ef4444';
  return '#14b8a6';
}

function getDueDateSortValue(dueDate: string | null) {
  if (!dueDate) return Number.POSITIVE_INFINITY;
  const parsed = new Date(dueDate).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const currentUserId = useMemo(() => Number(user?.id ?? 0), [user?.id]);
  const { data: projects, loading: loadingProjects, error: errorProjects, refetch: refetchProjects } = useApiProjects();
  const { data: tasks, loading: loadingTasks, statuses, refetch: refetchTasks } = useApiTasks();
  const { data: boards, loading: loadingBoards } = useApiBoards();
  const { data: myProjectMemberships, loading: loadingMemberships } = useApiProjectMembers(undefined, Number.isNaN(currentUserId) || currentUserId <= 0 ? undefined : currentUserId);
  const taskIds = useMemo(() => (tasks ?? []).map((task) => task.id_task), [tasks]);
  const { data: taskAssignments } = useApiTaskAssignments(taskIds);
  const { data: warnings } = useApiTaskWarnings({ status: 'active' });
  const { data: pushes } = useApiGithubPushes();
  const isStakeholderUser = user?.role === 'stakeholder';
  const isAdminUser = user?.role === 'admin';

  const loading = loadingProjects || loadingTasks || loadingBoards || (isAdminUser ? false : loadingMemberships);

  const visibleProjectIds = useMemo(() => {
    if (isAdminUser) {
      return new Set<number>((projects ?? []).map((project) => project.id_project));
    }
    const ids = new Set<number>();
    (myProjectMemberships ?? []).forEach((member) => ids.add(member.project));
    return ids;
  }, [isAdminUser, projects, myProjectMemberships]);

  const visibleProjects = useMemo(
    () => (projects ?? []).filter((project) => visibleProjectIds.has(project.id_project)),
    [projects, visibleProjectIds],
  );

  const projectById = useMemo(() => {
    const map = new Map<number, { id_project: number; name: string; created_by: number | null }>();
    visibleProjects.forEach((project) => {
      map.set(project.id_project, {
        id_project: project.id_project,
        name: project.name,
        created_by: project.created_by,
      });
    });
    return map;
  }, [visibleProjects]);

  const boardProjectMap = useMemo(() => {
    const map = new Map<number, number>();
    (boards ?? []).forEach((board) => {
      map.set(board.id_board, board.project);
    });
    return map;
  }, [boards]);

  const involvedProjectIds = useMemo(() => {
    return new Set<number>(visibleProjectIds);
  }, [visibleProjectIds]);

  const scopedTasks = useMemo(() => {
    const list = tasks ?? [];
    if (involvedProjectIds.size === 0) return [];
    return list.filter((task) => {
      const projectId = boardProjectMap.get(task.board ?? 0);
      return projectId != null && involvedProjectIds.has(projectId);
    });
  }, [tasks, boardProjectMap, involvedProjectIds]);

  const scopedTaskIdSet = useMemo(() => new Set(scopedTasks.map((task) => task.id_task)), [scopedTasks]);

  const scopedWarnings = useMemo(
    () => (warnings ?? []).filter((warning) => scopedTaskIdSet.has(warning.task)),
    [warnings, scopedTaskIdSet],
  );

  const taskStatusNameById = useMemo(() => {
    const map = new Map<number, string>();
    statuses.forEach((status) => {
      map.set(status.id_status, status.name);
    });
    return map;
  }, [statuses]);

  const refetchAll = () => { refetchProjects(); refetchTasks(); };

  // ── Derived KPIs ──
  const kpis = useMemo(() => {
    const pList = visibleProjects.filter((project) => shouldShowInGenericProjectDisplays(project.status));
    const tList = scopedTasks;
    const now = new Date();

    const totalProjects = pList.length;
    const totalTasks = tList.length;
    const completedTasks = tList.filter((t) => t.completed_at != null).length;
    const overdueTasks = tList.filter((t) => {
      if (t.completed_at) return false;
      if (!t.due_date) return false;
      return new Date(t.due_date) < now;
    }).length;
    const openTasks = totalTasks - completedTasks;

    return { totalProjects, totalTasks, completedTasks, openTasks, overdueTasks };
  }, [visibleProjects, scopedTasks]);

  const activeWarningsCount = scopedWarnings.length;
  const myTasks = useMemo(() => {
    if (!user) return [];
    const currentUserId = Number(user.id);
    const assignmentMap = new Map<number, Set<number>>();

    (taskAssignments ?? []).forEach((assignment) => {
      const existing = assignmentMap.get(assignment.task) ?? new Set<number>();
      existing.add(assignment.assigned_to);
      assignmentMap.set(assignment.task, existing);
    });

    return scopedTasks.filter((task) => {
      if (task.completed_at) return false;
      const assignedUsers = assignmentMap.get(task.id_task);
      if (assignedUsers && assignedUsers.size > 0) {
        return assignedUsers.has(currentUserId);
      }
      return task.assigned_to === currentUserId;
    }).sort((a, b) => getDueDateSortValue(a.due_date) - getDueDateSortValue(b.due_date));
  }, [scopedTasks, taskAssignments, user]);
  const [myTasksPage, setMyTasksPage] = useState(0);
  const [pushesPage, setPushesPage] = useState(0);

  const paginatedMyTasks = useMemo(() => {
    const start = myTasksPage * DASHBOARD_PANEL_BATCH_SIZE;
    return myTasks.slice(start, start + DASHBOARD_PANEL_BATCH_SIZE);
  }, [myTasks, myTasksPage]);

  const paginatedPushes = useMemo(() => {
    const start = pushesPage * DASHBOARD_PANEL_BATCH_SIZE;
    return (pushes ?? []).slice(start, start + DASHBOARD_PANEL_BATCH_SIZE);
  }, [pushes, pushesPage]);

  const myTasksTotalPages = Math.max(1, Math.ceil(myTasks.length / DASHBOARD_PANEL_BATCH_SIZE));
  const pushesTotalPages = Math.max(1, Math.ceil((pushes ?? []).length / DASHBOARD_PANEL_BATCH_SIZE));

  // ── Task distribution by status for chart ──
  const statusChartData = useMemo(() => {
    if (scopedTasks.length === 0 || statuses.length === 0) return [];
    const counts = new Map<number, number>();
    for (const t of scopedTasks) {
      const sid = t.status ?? 0;
      counts.set(sid, (counts.get(sid) ?? 0) + 1);
    }
    return statuses.map((s) => ({
      name: s.name,
      count: counts.get(s.id_status) ?? 0,
      color: getTaskStatusChartColor(s.name),
    }));
  }, [scopedTasks, statuses]);

  const upcomingProjects = useMemo(() => {
    if (!visibleProjects) return [];

    return [...visibleProjects]
      .filter((project) => shouldShowInGenericProjectDisplays(project.status))
      .sort(compareProjectsForGenericPriority);
  }, [visibleProjects]);

  const projectHealthMap = useMemo(() => {
    const map = new Map<number, { progress: { completed: number; total: number; percentage: number }; health: ProjectHealth }>();
    const taskList = tasks ?? [];
    const boardList = boards ?? [];
    upcomingProjects.forEach((project) => {
      const progress = computeProjectProgress(project.id_project, taskList, boardList);
      const health = getProjectHealth(project, progress);
      map.set(project.id_project, { progress, health });
    });
    return map;
  }, [upcomingProjects, tasks, boards]);

  // ── Pie data: project status distribution ──
  const projectStatusData = useMemo(() => {
    if (!visibleProjects) return [];
    const trackedStatuses = ['planning', 'in_progress', 'review', 'completed'] as const;
    const isTrackedStatus = (status: string): status is (typeof trackedStatuses)[number] => trackedStatuses.includes(status as (typeof trackedStatuses)[number]);
    const counts = new Map<string, number>();

    for (const project of visibleProjects) {
      const normalized = normalizeProjectStatus(project.status);
      if (!normalized || !isTrackedStatus(normalized)) continue;
      counts.set(normalized, (counts.get(normalized) ?? 0) + 1);
    }

    return trackedStatuses
      .filter((status) => (counts.get(status) ?? 0) > 0)
      .map((status) => ({
        key: status,
        name: getProjectStatusLabel(status),
        value: counts.get(status) ?? 0,
        color: getProjectStatusChartColor(status),
      }));
  }, [visibleProjects]);

  const isAuthExpiredError = useMemo(() => {
    if (!errorProjects) return false;
    const normalized = errorProjects.toLowerCase();
    return normalized.includes('token') || normalized.includes('sesion') || normalized.includes('sesión') || normalized.includes('expir') || normalized.includes('venc');
  }, [errorProjects]);

  if (errorProjects) {
    return (
      <div className="px-4 pt-10 text-center">
        <AlertTriangle className="w-8 h-8 text-destructive mx-auto mb-2" />
        <p className="text-[13px] text-destructive">{isAuthExpiredError ? 'Tu sesión venció. Vuelve a iniciar sesión.' : errorProjects}</p>
        <button
          onClick={() => {
            if (isAuthExpiredError) {
              window.location.href = '/';
              return;
            }
            refetchAll();
          }}
          className="mt-3 text-[12px] text-primary hover:underline"
        >
          {isAuthExpiredError ? 'Ir al inicio' : 'Reintentar'}
        </button>
      </div>
    );
  }

  return (
    <div className="px-4 pb-6 pt-3 max-w-[1600px] min-h-full flex flex-col gap-3">
      <CommandBar
        actions={[
          { label: 'Actualizar', icon: <RefreshCw className="w-3.5 h-3.5" />, onClick: () => refetchAll() },
        ]}
        rightSlot={
          <span className="text-xs text-muted-foreground">
            Hola, <span className="font-medium text-foreground">{user?.name?.split(' ')[0]}</span>
          </span>
        }
      />

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-[4px] h-[80px] animate-pulse" />
          ))
        ) : (
          [
            { title: 'Proyectos', value: kpis.totalProjects, subtitle: 'total activos', icon: <Briefcase className="w-4 h-4" />, accentColor: 'primary' as const },
            { title: 'Tareas', value: kpis.totalTasks, subtitle: 'en tus proyectos', icon: <ListChecks className="w-4 h-4" />, accentColor: 'info' as const },
            { title: 'Completadas', value: kpis.completedTasks, subtitle: 'tareas terminadas', icon: <CheckCircle2 className="w-4 h-4" />, accentColor: 'success' as const },
            { title: 'Pendientes', value: kpis.openTasks, subtitle: 'tareas abiertas', icon: <Timer className="w-4 h-4" />, accentColor: 'warning' as const },
            { title: 'Vencidas', value: kpis.overdueTasks, subtitle: 'requieren atención', icon: <AlertTriangle className="w-4 h-4" />, accentColor: 'destructive' as const },
            { title: 'Warnings', value: activeWarningsCount, subtitle: 'alertas en tus tareas', icon: <AlertTriangle className="w-4 h-4 text-warning" />, accentColor: 'warning' as const },
          ].map((kpi, i) => (
            <motion.div
              key={kpi.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: i * 0.05, ease: 'easeOut' }}
            >
              <KPICard
                title={kpi.title}
                value={kpi.value}
                subtitle={kpi.subtitle}
                icon={kpi.icon}
                accentColor={kpi.accentColor}
              />
            </motion.div>
          ))
        )}
      </div>

      {/* Charts row: Estado de Proyectos + Tareas por Estado side by side */}
      <div className="grid lg:grid-cols-2 gap-3 items-stretch">

        {/* Estado de Proyectos */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.35, ease: 'easeOut' }}
          className="bg-card border border-border rounded-[4px] p-4 min-h-[220px] h-full flex flex-col"
        >
          <h2 className="text-[13px] font-semibold text-foreground mb-2">Estado de Proyectos</h2>
          {projectStatusData.length > 0 ? (
            <>
              <div className="h-[180px] min-h-[180px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={projectStatusData} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="value" paddingAngle={2}>
                      {projectStatusData.map((item) => (
                        <Cell key={item.key} fill={item.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--foreground)', fontSize: '11px' }}
                      labelStyle={{ color: 'var(--foreground)' }}
                      itemStyle={{ color: 'var(--foreground)' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-wrap justify-center gap-3 mt-1">
                {projectStatusData.map((d) => (
                  <span key={d.name} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
                    {d.name} ({d.value})
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-[11px] text-muted-foreground py-8 text-center">Sin proyectos.</p>
          )}
        </motion.div>

        {/* Tareas por Estado */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: 0.32, ease: 'easeOut' }}
          className="bg-card border border-border rounded-[4px] p-4 min-h-[220px] h-full flex flex-col"
        >
          <h2 className="text-[13px] font-semibold text-foreground mb-2">Tareas por Estado</h2>
          <div className="flex-1 min-h-[180px]">
            {statusChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statusChartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" stroke="var(--muted-foreground)" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--muted-foreground)" fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--foreground)', fontSize: '11px' }}
                    labelStyle={{ color: 'var(--foreground)' }}
                    itemStyle={{ color: 'var(--foreground)' }}
                  />
                  <Bar dataKey="count" name="Tareas" radius={[2, 2, 0, 0]}>
                    {statusChartData.map((entry) => (
                      <Cell key={`status-bar-${entry.name}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-[11px] text-muted-foreground py-8 text-center">Sin datos de tareas.</p>
            )}
          </div>
        </motion.div>
      </div>

      {/* Full-width projects table */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.3, ease: 'easeOut' }}
        className="bg-card border border-border rounded-[4px] flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-border">
          <h2 className="text-[13px] font-semibold text-foreground">Proyectos</h2>
          <Link
            to="/projects"
            className="text-[11px] text-primary hover:underline font-medium inline-flex items-center gap-1"
          >
            Ver todos <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : visibleProjects.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-muted-foreground">No hay proyectos registrados.</div>
        ) : (
          <div className="flex flex-col">
            <div className="grid grid-cols-[minmax(0,2fr)_minmax(112px,0.9fr)_minmax(110px,1.1fr)_44px_minmax(110px,0.85fr)_minmax(78px,0.6fr)] gap-3 border-b border-border bg-surface-secondary/50 px-4 py-1.5">
              <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Proyecto</span>
              <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Estado</span>
              <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Progreso</span>
              <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Salud</span>
              <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Fecha Fin</span>
              <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Días rest.</span>
            </div>
            <div className="max-h-[360px] overflow-y-auto scrollbar-app divide-y divide-border">
              {upcomingProjects.map((project) => {
                const dl = getProjectDaysLabel(project.end_date, project.status);
                const ph = projectHealthMap.get(project.id_project);
                const pct = ph?.progress.percentage ?? 0;
                const hasTasks = (ph?.progress.total ?? 0) > 0;
                const health = ph?.health ?? 'yellow';
                return (
                  <button
                    key={project.id_project}
                    type="button"
                    className="grid w-full grid-cols-[minmax(0,2fr)_minmax(112px,0.9fr)_minmax(110px,1.1fr)_44px_minmax(110px,0.85fr)_minmax(78px,0.6fr)] items-center gap-3 px-4 py-1.5 hover:bg-accent/30 transition-colors text-left"
                    onClick={() => navigate(`/projects/${project.id_project}`)}
                  >
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-foreground truncate">{project.name}</p>
                    </div>
                    <div className="min-w-0">
                      <StatusBadge status={getProjectStatusBadge(project.status)} text={getProjectStatusLabel(project.status)} size="sm" />
                    </div>
                    <div className="min-w-0 flex items-center gap-2">
                      <ProgressBar value={pct} height={5} className="flex-1" />
                      <span className="text-[10px] font-medium text-muted-foreground tabular-nums whitespace-nowrap">
                        {hasTasks ? `${pct}%` : '—'}
                      </span>
                    </div>
                    <div className="flex justify-start" title={HEALTH_LABEL[health]}>
                      <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${HEALTH_DOT_CLASS[health]}`} />
                    </div>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap">{formatProjectDate(project.end_date)}</span>
                    <span className={`text-[11px] ${dl.cls}`}>{dl.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </motion.div>

      {/* Bottom row: My Tasks + Recent Activity */}
      {!isStakeholderUser && (
      <div className="grid xl:grid-cols-2 gap-3 items-start">
          {/* My Tasks */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.4, ease: 'easeOut' }}
            className="bg-card border border-border rounded-[4px] flex flex-col"
          >
            <div className="flex items-center justify-between px-4 py-2 border-b border-border">
              <h2 className="text-[13px] font-semibold text-foreground">Mis Tareas Pendientes</h2>
              <Link to="/backlog" className="text-[11px] text-primary hover:underline font-medium inline-flex items-center gap-1">
                Ver Backlog <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            {loadingTasks ? (
              <div className="p-4 space-y-2">
                {[1, 2, 3].map((i) => <div key={i} className="h-6 animate-pulse bg-secondary rounded" />)}
              </div>
            ) : myTasks.length === 0 ? (
              <div className="py-8 text-center text-[12px] text-muted-foreground">Sin tareas pendientes.</div>
            ) : (
              <>
                <div className="max-h-[360px] overflow-y-auto scrollbar-app divide-y divide-border">
                  {paginatedMyTasks.map((task) => {
                    const isOverdue = task.due_date && new Date(task.due_date) < new Date();
                    const taskProjectId = boardProjectMap.get(task.board ?? 0);
                    const taskProjectName = taskProjectId ? (projectById.get(taskProjectId)?.name ?? `Proyecto #${taskProjectId}`) : 'Proyecto sin identificar';
                    const taskStatusLabel = task.status != null ? (taskStatusNameById.get(task.status) ?? `Estado #${task.status}`) : 'Sin estado';
                    const taskStatusColor = getTaskStatusChartColor(taskStatusLabel);
                    return (
                      <button
                        key={task.id_task}
                        type="button"
                        className="w-full px-4 py-2 hover:bg-accent/30 transition-colors flex items-center gap-3 min-h-0 text-left"
                        onClick={() => {
                          if (!taskProjectId) return;
                          navigate(`/projects/${taskProjectId}?tab=tareas&task=${task.id_task}`);
                        }}
                      >
                        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: taskStatusColor }} />
                        <div className="flex-1 min-w-0">
                          <p className="text-[12px] font-medium text-foreground truncate">{task.title}</p>
                          <div className="flex items-center gap-2 mt-0.5 min-w-0">
                            <p className="text-[10px] text-muted-foreground truncate">{taskProjectName}</p>
                            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-secondary text-muted-foreground whitespace-nowrap">
                              {taskStatusLabel}
                            </span>
                          </div>
                        </div>
                        {task.due_date && (
                          <span className={`text-[10px] whitespace-nowrap ${isOverdue ? 'text-destructive font-semibold' : 'text-muted-foreground'}`}>
                            {formatProjectDate(task.due_date)}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>

                {myTasksTotalPages > 1 && (
                  <div className="flex items-center justify-between px-4 py-2 border-t border-border">
                    <span className="text-[10px] text-muted-foreground">Página {myTasksPage + 1} de {myTasksTotalPages}</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setMyTasksPage((page) => Math.max(0, page - 1))}
                        disabled={myTasksPage === 0}
                        className="h-6 px-2 border border-border rounded-[3px] text-[10px] font-medium text-foreground hover:bg-surface-secondary transition-colors disabled:opacity-50"
                      >
                        Anterior
                      </button>
                      <button
                        type="button"
                        onClick={() => setMyTasksPage((page) => Math.min(myTasksTotalPages - 1, page + 1))}
                        disabled={myTasksPage >= myTasksTotalPages - 1}
                        className="h-6 px-2 border border-border rounded-[3px] text-[10px] font-medium text-foreground hover:bg-surface-secondary transition-colors disabled:opacity-50"
                      >
                        Siguiente
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </motion.div>

          {/* Recent Push Activity */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.45, ease: 'easeOut' }}
          className="bg-card border border-border rounded-[4px] flex flex-col"
        >
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            <h2 className="text-[13px] font-semibold text-foreground">Actividad Reciente (Git)</h2>
          </div>
          {!pushes || pushes.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-muted-foreground">Sin push events recientes.</div>
          ) : (
            <>
              <div className="max-h-[360px] overflow-y-auto scrollbar-app divide-y divide-border">
                {paginatedPushes.map((push) => {
                  const commitCount = Array.isArray(push.commits) ? push.commits.length : 0;
                  return (
                    <div key={push.id_push} className="px-4 py-2 hover:bg-accent/30 transition-colors min-h-0">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-medium text-foreground">{push.pusher ?? 'unknown'}</span>
                        <span className="text-[10px] font-mono text-primary bg-primary/10 px-1.5 py-0.5 rounded-[2px]">
                          {push.ref?.replace('refs/heads/', '') ?? 'main'}
                        </span>
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {commitCount} commit{commitCount !== 1 ? 's' : ''} · {new Date(push.received_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  );
                })}
              </div>

              {pushesTotalPages > 1 && (
                <div className="flex items-center justify-between px-4 py-2 border-t border-border">
                  <span className="text-[10px] text-muted-foreground">Página {pushesPage + 1} de {pushesTotalPages}</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setPushesPage((page) => Math.max(0, page - 1))}
                      disabled={pushesPage === 0}
                      className="h-6 px-2 border border-border rounded-[3px] text-[10px] font-medium text-foreground hover:bg-surface-secondary transition-colors disabled:opacity-50"
                    >
                      Anterior
                    </button>
                    <button
                      type="button"
                      onClick={() => setPushesPage((page) => Math.min(pushesTotalPages - 1, page + 1))}
                      disabled={pushesPage >= pushesTotalPages - 1}
                      className="h-6 px-2 border border-border rounded-[3px] text-[10px] font-medium text-foreground hover:bg-surface-secondary transition-colors disabled:opacity-50"
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </motion.div>
      </div>
      )}
    </div>
  );
}
