import { useMemo, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line,
} from 'recharts';
import {
  BarChart3, CheckCircle2, Timer, AlertTriangle,
  Download, RefreshCw, Loader2, TrendingUp, Clock,
} from 'lucide-react';
import { KPICard } from '../components/KPICard';
import { CommandBar } from '../components/CommandBar';
import {
  useApiProjects, useApiTasks, useApiTaskWarnings, useApiBoards,
} from '../hooks/useProjectData';

const CHART_COLORS = ['#D4192C', '#F59E0B', '#10B981', '#6366F1', '#8B5CF6', '#EC4899', '#14B8A6'];

export default function Reports() {
  const { data: projects, loading: loadingProjects, refetch: refetchProjects } = useApiProjects();
  const { data: tasks, loading: loadingTasks, statuses, priorities, refetch: refetchTasks } = useApiTasks();
  const { data: warnings, refetch: refetchWarnings } = useApiTaskWarnings();
  const { data: boards } = useApiBoards();
  const [selectedProject, setSelectedProject] = useState<number | null>(null);

  const loading = loadingProjects || loadingTasks;
  const refetchAll = () => { refetchProjects(); refetchTasks(); refetchWarnings(); };

  // Build board→project lookup for filtering tasks by project
  const boardProjectMap = useMemo(() => {
    const m = new Map<number, number>();
    (boards ?? []).forEach((b) => m.set(b.id_board, b.project));
    return m;
  }, [boards]);

  // Filter tasks by project via board→project mapping
  const filteredTasks = useMemo(() => {
    const t = tasks ?? [];
    if (!selectedProject) return t;
    return t.filter((task) => boardProjectMap.get(task.board ?? 0) === selectedProject);
  }, [tasks, selectedProject, boardProjectMap]);

  // Filter warnings by project via task→board→project chain
  const filteredWarnings = useMemo(() => {
    const w = warnings ?? [];
    if (!selectedProject) return w;
    const taskIds = new Set(filteredTasks.map((t) => t.id_task));
    return w.filter((wr) => taskIds.has(wr.task));
  }, [warnings, selectedProject, filteredTasks]);

  // ── KPIs ──
  const kpis = useMemo(() => {
    const tList = filteredTasks;
    const now = new Date();
    const totalTasks = tList.length;
    const completedTasks = tList.filter((t) => t.completed_at != null).length;
    const overdueTasks = tList.filter((t) => !t.completed_at && t.due_date && new Date(t.due_date) < now).length;
    const completionRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

    // Average completion time (days)
    const completedWithDates = tList.filter((t) => t.completed_at && t.created_at);
    const avgDays = completedWithDates.length > 0
      ? Math.round(completedWithDates.reduce((sum, t) => {
          const created = new Date(t.created_at).getTime();
          const completed = new Date(t.completed_at!).getTime();
          return sum + (completed - created) / (1000 * 60 * 60 * 24);
        }, 0) / completedWithDates.length)
      : 0;

    const activeWarnings = filteredWarnings.filter((w) => w.status === 'active').length;

    return { totalTasks, completedTasks, overdueTasks, completionRate, avgDays, activeWarnings };
  }, [filteredTasks, filteredWarnings]);

  // ── Status distribution chart data ──
  const statusChartData = useMemo(() => {
    if (!filteredTasks.length || !statuses.length) return [];
    const counts = new Map<number, number>();
    for (const t of filteredTasks) {
      const sid = t.status ?? 0;
      counts.set(sid, (counts.get(sid) ?? 0) + 1);
    }
    return statuses.map((s) => ({
      name: s.name,
      value: counts.get(s.id_status) ?? 0,
    })).filter((d) => d.value > 0);
  }, [filteredTasks, statuses]);

  // ── Priority distribution chart data ──
  const priorityChartData = useMemo(() => {
    if (!filteredTasks.length || !priorities.length) return [];
    const counts = new Map<number, number>();
    for (const t of filteredTasks) {
      const pid = t.priority ?? 0;
      counts.set(pid, (counts.get(pid) ?? 0) + 1);
    }
    return priorities.map((p) => ({
      name: p.name,
      value: counts.get(p.id_priority) ?? 0,
    })).filter((d) => d.value > 0);
  }, [filteredTasks, priorities]);

  // ── Weekly velocity (tasks completed per week, last 8 weeks) ──
  const velocityData = useMemo(() => {
    const completed = filteredTasks.filter((t) => t.completed_at);
    const now = new Date();
    const weeks: { label: string; count: number }[] = [];
    for (let i = 7; i >= 0; i--) {
      const weekStart = new Date(now);
      weekStart.setDate(weekStart.getDate() - (i + 1) * 7);
      const weekEnd = new Date(now);
      weekEnd.setDate(weekEnd.getDate() - i * 7);
      const count = completed.filter((t) => {
        const d = new Date(t.completed_at!);
        return d >= weekStart && d < weekEnd;
      }).length;
      weeks.push({
        label: `S${8 - i}`,
        count,
      });
    }
    return weeks;
  }, [filteredTasks]);

  // ── Warnings over time (last 30 days, grouped by week) ──
  const warningsTimeData = useMemo(() => {
    const w = filteredWarnings;
    const now = new Date();
    const weeks: { label: string; active: number; resolved: number }[] = [];
    for (let i = 3; i >= 0; i--) {
      const weekStart = new Date(now);
      weekStart.setDate(weekStart.getDate() - (i + 1) * 7);
      const weekEnd = new Date(now);
      weekEnd.setDate(weekEnd.getDate() - i * 7);
      const inRange = w.filter((wr) => {
        const d = new Date(wr.created_at);
        return d >= weekStart && d < weekEnd;
      });
      weeks.push({
        label: `S${4 - i}`,
        active: inRange.filter((wr) => wr.status === 'active').length,
        resolved: inRange.filter((wr) => wr.status === 'resolved').length,
      });
    }
    return weeks;
  }, [filteredWarnings]);

  // ── Export CSV ──
  const exportCSV = () => {
    const rows = filteredTasks.map((t) => ({
      id: t.id_task,
      title: t.title,
      status: statuses.find((s) => s.id_status === t.status)?.name ?? '',
      priority: priorities.find((p) => p.id_priority === t.priority)?.name ?? '',
      assigned_to: t.assigned_to ?? '',
      due_date: t.due_date ?? '',
      completed_at: t.completed_at ?? '',
      created_at: t.created_at,
    }));
    const headers = Object.keys(rows[0] ?? {});
    const csv = [
      headers.join(','),
      ...rows.map((r) => headers.map((h) => `"${String(r[h as keyof typeof r]).replace(/"/g, '""')}"`).join(',')),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reporte-tareas-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Project filter pills ──
  const projectFilters = useMemo(() => {
    const pList = projects ?? [];
    return [
      {
        label: 'Todos',
        active: selectedProject === null,
        count: filteredTasks.length,
        onClick: () => setSelectedProject(null),
      },
      ...pList.map((p) => ({
        label: p.name,
        active: selectedProject === p.id_project,
        onClick: () => setSelectedProject(p.id_project),
      })),
    ];
  }, [projects, selectedProject, filteredTasks.length]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="text-[13px]">Cargando reportes…</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <CommandBar
        actions={[
          { label: 'Exportar CSV', icon: <Download className="w-3.5 h-3.5" />, onClick: exportCSV },
          { label: 'Refrescar', icon: <RefreshCw className="w-3.5 h-3.5" />, onClick: refetchAll },
        ]}
        filters={projectFilters}
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard
            title="Total Tareas"
            value={kpis.totalTasks}
            icon={<BarChart3 className="w-4 h-4" />}
          />
          <KPICard
            title="Completadas"
            value={kpis.completedTasks}
            icon={<CheckCircle2 className="w-4 h-4" />}
            trend={kpis.completionRate > 50 ? 'up' : 'down'}
            trendValue={`${kpis.completionRate}%`}
          />
          <KPICard
            title="Vencidas"
            value={kpis.overdueTasks}
            icon={<Timer className="w-4 h-4" />}
            trend={kpis.overdueTasks === 0 ? 'up' : 'down'}
          />
          <KPICard
            title="Tasa Completado"
            value={`${kpis.completionRate}%`}
            icon={<TrendingUp className="w-4 h-4" />}
          />
          <KPICard
            title="Tiempo Promedio"
            value={`${kpis.avgDays}d`}
            subtitle="días para completar"
            icon={<Clock className="w-4 h-4" />}
          />
          <KPICard
            title="Warnings Activos"
            value={kpis.activeWarnings}
            icon={<AlertTriangle className="w-4 h-4" />}
            trend={kpis.activeWarnings === 0 ? 'up' : 'down'}
          />
        </div>

        {/* Charts row 1: Velocity + Status */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Velocity Bar Chart */}
          <div className="bg-card border border-border rounded-[4px] p-4">
            <h3 className="text-[12px] font-semibold text-foreground mb-3">
              Velocidad de Completado (últimas 8 semanas)
            </h3>
            {velocityData.some((d) => d.count > 0) ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={velocityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--card)',
                      border: '1px solid var(--border)',
                      borderRadius: '4px',
                      fontSize: '11px',
                    }}
                  />
                  <Bar dataKey="count" name="Completadas" fill="#D4192C" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[220px] text-[12px] text-muted-foreground">
                Sin datos de completado
              </div>
            )}
          </div>

          {/* Status Pie Chart */}
          <div className="bg-card border border-border rounded-[4px] p-4">
            <h3 className="text-[12px] font-semibold text-foreground mb-3">
              Distribución por Estado
            </h3>
            {statusChartData.length > 0 ? (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width="50%" height={220}>
                  <PieChart>
                    <Pie
                      data={statusChartData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      innerRadius={40}
                      strokeWidth={1}
                    >
                      {statusChartData.map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--card)',
                        border: '1px solid var(--border)',
                        borderRadius: '4px',
                        fontSize: '11px',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-1.5">
                  {statusChartData.map((d, i) => (
                    <div key={d.name} className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
                      />
                      <span className="text-[11px] text-muted-foreground flex-1 truncate">{d.name}</span>
                      <span className="text-[11px] font-medium text-foreground">{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-[220px] text-[12px] text-muted-foreground">
                Sin datos de estado
              </div>
            )}
          </div>
        </div>

        {/* Charts row 2: Priority + Warnings Trend */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Priority Bar Chart */}
          <div className="bg-card border border-border rounded-[4px] p-4">
            <h3 className="text-[12px] font-semibold text-foreground mb-3">
              Distribución por Prioridad
            </h3>
            {priorityChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={priorityChartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} width={80} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--card)',
                      border: '1px solid var(--border)',
                      borderRadius: '4px',
                      fontSize: '11px',
                    }}
                  />
                  <Bar dataKey="value" name="Tareas" fill="#6366F1" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[220px] text-[12px] text-muted-foreground">
                Sin datos de prioridad
              </div>
            )}
          </div>

          {/* Warnings Trend Line Chart */}
          <div className="bg-card border border-border rounded-[4px] p-4">
            <h3 className="text-[12px] font-semibold text-foreground mb-3">
              Tendencia de Warnings (últimas 4 semanas)
            </h3>
            {warningsTimeData.some((d) => d.active > 0 || d.resolved > 0) ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={warningsTimeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--card)',
                      border: '1px solid var(--border)',
                      borderRadius: '4px',
                      fontSize: '11px',
                    }}
                  />
                  <Line type="monotone" dataKey="active" name="Activos" stroke="#F59E0B" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="resolved" name="Resueltos" stroke="#10B981" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[220px] text-[12px] text-muted-foreground">
                Sin datos de warnings
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
