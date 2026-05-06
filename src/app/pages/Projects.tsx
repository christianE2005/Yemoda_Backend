import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { motion } from 'motion/react';
import {
  Plus, Search, Calendar, X, LayoutGrid, List, Loader2, ArrowUpDown,
} from 'lucide-react';
import { StatusBadge } from '../components/StatusBadge';
import { DatePickerField } from '../components/DatePickerField';
import { ProgressBar } from '../components/ProgressBar';
import { useApiBoards, useApiProjectMembers, useApiProjects, useApiTasks } from '../hooks/useProjectData';
import { useAuth } from '../context/AuthContext';
import { projectsService, usersService } from '../../services';
import { compareProjectsForGenericPriority, getProjectStatusBadge, getProjectStatusLabel, isTerminalProjectStatus, normalizeProjectStatus, PROJECT_STATUS_OPTIONS } from '../utils/projectStatus';
import { formatProjectDate } from '../utils/projectDates';
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

const PROJECTS_BATCH_SIZE = 8;
type ProjectsSort = 'nearest_due' | 'farthest_due' | 'name_asc' | 'name_desc';

function getProjectsRemainingLabel(endDate: string | null, status?: string | null) {
  if (!endDate) return { label: '—', cls: 'text-muted-foreground' };
  if (isTerminalProjectStatus(status)) return { label: '—', cls: 'text-muted-foreground' };

  const days = Math.ceil((new Date(endDate).getTime() - Date.now()) / 86_400_000);
  if (Number.isNaN(days)) return { label: '—', cls: 'text-muted-foreground' };
  if (days < 0) return { label: 'Vencido', cls: 'text-destructive font-semibold' };
  if (days === 0) return { label: 'Hoy', cls: 'text-destructive font-semibold' };

  if (days >= 365) {
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);
    const label = `${years}a${months > 0 ? ` ${months}m` : ''}`;
    return { label, cls: 'text-muted-foreground' };
  }

  if (days >= 30) {
    const months = Math.floor(days / 30);
    const remDays = days % 30;
    const label = `${months}m${remDays > 0 ? ` ${remDays}d` : ''}`;
    return { label, cls: 'text-muted-foreground' };
  }

  return { label: `${days}d`, cls: days <= 7 ? 'text-warning font-semibold' : 'text-muted-foreground' };
}

export default function Projects() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const membershipUserId = Number(user?.id ?? -1);
  const isAdminUser = user?.role === 'admin';
  const canCreateProjects = user?.role === 'admin' || user?.role === 'user' || user?.role === 'project_manager';
  const { data: projects, loading, refetch } = useApiProjects();
  const { data: memberRows, loading: loadingMemberRows, refetch: refetchMemberRows } = useApiProjectMembers(undefined, membershipUserId);
  const { data: tasks } = useApiTasks();
  const { data: boards } = useApiBoards();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('list');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState<ProjectsSort>('nearest_due');
  const [creating, setCreating] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const tomorrowDate = useMemo(() => {
    const next = new Date();
    next.setDate(next.getDate() + 1);
    return next.toISOString().slice(0, 10);
  }, []);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formEnd, setFormEnd] = useState('');

  const visibleProjects = useMemo(() => {
    if (!projects) return [];
    if (isAdminUser) return projects;
    const allowedProjectIds = new Set((memberRows ?? []).map((member) => member.project));
    return projects.filter((project) => allowedProjectIds.has(project.id_project));
  }, [projects, memberRows, isAdminUser]);

  const projectHealthMap = useMemo(() => {
    const map = new Map<number, { progress: { completed: number; total: number; percentage: number }; health: ProjectHealth }>();
    const taskList = tasks ?? [];
    const boardList = boards ?? [];
    visibleProjects.forEach((project) => {
      const progress = computeProjectProgress(project.id_project, taskList, boardList);
      const health = getProjectHealth(project, progress);
      map.set(project.id_project, { progress, health });
    });
    return map;
  }, [visibleProjects, tasks, boards]);

  const filteredProjects = useMemo(() => {
    if (!visibleProjects) return [];
    const normalizedSearch = searchTerm.trim().toLowerCase();

    const matches = visibleProjects.filter((p) => {
      const statusLabel = getProjectStatusLabel(p.status).toLowerCase();
      const description = (p.description ?? '').toLowerCase();
      const matchSearch = !normalizedSearch
        || p.name.toLowerCase().includes(normalizedSearch)
        || description.includes(normalizedSearch)
        || statusLabel.includes(normalizedSearch);
      const matchStatus = statusFilter === 'all' || normalizeProjectStatus(p.status) === statusFilter;
      return matchSearch && matchStatus;
    });

    return matches.sort((left, right) => {
      const leftDue = left.end_date ? new Date(left.end_date).getTime() : Number.POSITIVE_INFINITY;
      const rightDue = right.end_date ? new Date(right.end_date).getTime() : Number.POSITIVE_INFINITY;
      const leftTerminal = isTerminalProjectStatus(left.status);
      const rightTerminal = isTerminalProjectStatus(right.status);

      switch (sortBy) {
        case 'farthest_due':
          if (leftTerminal !== rightTerminal) return leftTerminal ? 1 : -1;
          return rightDue - leftDue;
        case 'name_asc':
          if (leftTerminal !== rightTerminal) return leftTerminal ? 1 : -1;
          return left.name.localeCompare(right.name);
        case 'name_desc':
          if (leftTerminal !== rightTerminal) return leftTerminal ? 1 : -1;
          return right.name.localeCompare(left.name);
        case 'nearest_due':
        default:
          return compareProjectsForGenericPriority(left, right);
      }
    });
  }, [visibleProjects, searchTerm, sortBy, statusFilter]);

  const paginatedProjects = useMemo(() => {
    const start = currentPage * PROJECTS_BATCH_SIZE;
    return filteredProjects.slice(start, start + PROJECTS_BATCH_SIZE);
  }, [filteredProjects, currentPage]);

  const totalPages = Math.max(1, Math.ceil(filteredProjects.length / PROJECTS_BATCH_SIZE));

  // Unique status values for filter buttons
  const statusValues = useMemo(() => {
    if (!visibleProjects) return [] as typeof PROJECT_STATUS_OPTIONS;
    const unique = new Set(visibleProjects.map((p) => normalizeProjectStatus(p.status)).filter((status): status is NonNullable<typeof status> => Boolean(status)));
    return PROJECT_STATUS_OPTIONS.filter((option) => unique.has(option.value));
  }, [visibleProjects]);

  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>();
    visibleProjects.forEach((project) => {
      const normalizedStatus = normalizeProjectStatus(project.status);
      if (normalizedStatus) {
        counts.set(normalizedStatus, (counts.get(normalizedStatus) ?? 0) + 1);
      }
    });
    return counts;
  }, [visibleProjects]);

  const isLoadingPage = loading || (isAdminUser ? false : loadingMemberRows);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formEnd) {
      toast.error('La fecha de entrega es obligatoria');
      return;
    }
    setCreating(true);
    try {
      const createdProject = await projectsService.create({
        name: formName,
        description: formDesc || undefined,
        end_date: formEnd,
      });
      if (user?.id) {
        try {
          const creatorId = Number(user.id);
          const projectMembers = await usersService.listMembers(createdProject.id_project);
          const existingCreatorMember = projectMembers.find((member) => member.user === creatorId) ?? null;

          if (existingCreatorMember) {
            if (existingCreatorMember.role !== 1) {
              await usersService.updateMember(existingCreatorMember.id, { role: 1 });
            }
          } else {
            await usersService.addMember(createdProject.id_project, creatorId, 1);
          }
        } catch {
          toast.error('Proyecto creado, pero no se pudo asignar automáticamente como Project Manager.');
        }
      }
      toast.success('Proyecto creado exitosamente');
      setShowCreateModal(false);
      setFormName(''); setFormDesc(''); setFormEnd('');
      setSearchTerm('');
      setStatusFilter('all');
      setCurrentPage(0);
      refetch();
      refetchMemberRows();
    } catch {
      toast.error('Error al crear el proyecto');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="px-4 pb-6 pt-3 max-w-[1600px] min-h-full flex flex-col gap-4">
      <div className="bg-card border border-border rounded-[4px] p-3 flex flex-col gap-3">
        <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3">
          <div>
            <h1 className="text-[14px] font-semibold text-foreground">Proyectos</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Busca, filtra y ordena proyectos activos por fecha de entrega.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
            <div className="relative min-w-[240px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Buscar por proyecto, estado o descripción…"
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(0);
                }}
                className="w-full h-9 bg-surface-secondary border border-border rounded-[4px] pl-8 pr-3 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
              />
            </div>

            <div className="relative min-w-[190px]">
              <ArrowUpDown className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
              <select
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value as ProjectsSort);
                  setCurrentPage(0);
                }}
                className="w-full h-9 bg-surface-secondary border border-border rounded-[4px] pl-8 pr-3 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary/20"
              >
                <option value="nearest_due">Entrega más cercana</option>
                <option value="farthest_due">Entrega más lejana</option>
                <option value="name_asc">Nombre A-Z</option>
                <option value="name_desc">Nombre Z-A</option>
              </select>
            </div>

            <div className="flex items-center border border-border rounded-[4px] overflow-hidden shrink-0">
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={`h-9 w-10 flex items-center justify-center transition-colors ${viewMode === 'list' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:bg-accent hover:text-foreground'}`}
                title="Vista tabla"
              >
                <List className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('grid')}
                className={`h-9 w-10 flex items-center justify-center transition-colors ${viewMode === 'grid' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:bg-accent hover:text-foreground'}`}
                title="Vista tarjetas"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
            </div>

            {canCreateProjects && (
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="h-9 px-4 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[4px] text-[12px] font-semibold inline-flex items-center justify-center gap-2 transition-colors shrink-0"
              >
                <Plus className="w-4 h-4" />
                Nuevo Proyecto
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => { setStatusFilter('all'); setCurrentPage(0); }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-colors ${statusFilter === 'all' ? 'bg-primary text-primary-foreground' : 'bg-surface-secondary border border-border text-muted-foreground hover:text-foreground hover:bg-accent'}`}
          >
            Todos
            <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${statusFilter === 'all' ? 'bg-white/20 text-white' : 'bg-background text-muted-foreground'}`}>
              {visibleProjects.length}
            </span>
          </button>

          {statusValues.map((status) => (
            <button
              key={status.value}
              type="button"
              onClick={() => { setStatusFilter(status.value); setCurrentPage(0); }}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-colors ${statusFilter === status.value ? 'bg-primary text-primary-foreground' : 'bg-surface-secondary border border-border text-muted-foreground hover:text-foreground hover:bg-accent'}`}
            >
              {status.label}
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${statusFilter === status.value ? 'bg-white/20 text-white' : 'bg-background text-muted-foreground'}`}>
                {statusCounts.get(status.value) ?? 0}
              </span>
            </button>
          ))}
        </div>
      </div>

      {isLoadingPage ? (
        <div className="flex items-center justify-center py-24 flex-1">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : viewMode === 'list' ? (
        /* Table view */
        <div className="bg-card border border-border rounded-[4px] overflow-hidden">
          <div className="grid grid-cols-[minmax(0,2fr)_minmax(112px,0.9fr)_minmax(110px,1.1fr)_44px_minmax(110px,0.85fr)_minmax(78px,0.6fr)] gap-3 border-b border-border bg-surface-secondary/50 px-4 py-1.5">
            <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Proyecto</span>
            <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Estado</span>
            <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Progreso</span>
            <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Salud</span>
            <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Fecha Fin</span>
            <span className="text-left text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">Tiempo rest.</span>
          </div>

          <div className="overflow-y-auto scrollbar-app max-h-[600px] divide-y divide-border">
            {paginatedProjects.map((project, i) => {
              const dl = getProjectsRemainingLabel(project.end_date, project.status);
              const ph = projectHealthMap.get(project.id_project);
              const pct = ph?.progress.percentage ?? 0;
              const hasTasks = (ph?.progress.total ?? 0) > 0;
              const health = ph?.health ?? 'yellow';
              return (
                <motion.button
                  key={project.id_project}
                  type="button"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: i * 0.04, ease: 'easeOut' }}
                  className="grid w-full grid-cols-[minmax(0,2fr)_minmax(112px,0.9fr)_minmax(110px,1.1fr)_44px_minmax(110px,0.85fr)_minmax(78px,0.6fr)] items-center gap-3 px-4 py-1.5 hover:bg-accent/30 transition-colors text-left"
                  onClick={() => navigate(`/projects/${project.id_project}`)}
                >
                  <div className="min-w-0">
                    <p className="text-[12px] font-medium text-foreground truncate">{project.name}</p>
                    {project.description && (
                      <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-1">{project.description}</p>
                    )}
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
                  <span className={`text-[12px] ${dl.cls}`}>{dl.label}</span>
                </motion.button>
              );
            })}

            {filteredProjects.length === 0 && (
              <div className="px-4 py-8 text-center">
                <p className="text-[12px] font-medium text-foreground">Sin proyectos para mostrar</p>
                <p className="text-[11px] text-muted-foreground mt-1">No hay proyectos con los filtros actuales.</p>
              </div>
            )}
          </div>

        </div>
      ) : (
        /* Grid view */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 content-start min-h-0">
          {paginatedProjects.map((project, i) => {
            const dl = getProjectsRemainingLabel(project.end_date, project.status);
            const ph = projectHealthMap.get(project.id_project);
            const pct = ph?.progress.percentage ?? 0;
            const hasTasks = (ph?.progress.total ?? 0) > 0;
            const health = ph?.health ?? 'yellow';
            return (
              <motion.div
                key={project.id_project}
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: i * 0.06, ease: 'easeOut' }}
                className="min-h-0"
              >
                <Link
                  to={`/projects/${project.id_project}`}
                  className="bg-card border border-border hover:border-primary/40 transition-colors flex h-full min-h-[152px] flex-col rounded-[4px] p-3"
                >
                  <div className="flex items-start justify-between mb-2 gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`w-2.5 h-2.5 rounded-full shrink-0 ${HEALTH_DOT_CLASS[health]}`}
                        title={HEALTH_LABEL[health]}
                      />
                      <h3 className="text-[13px] font-semibold text-foreground leading-snug truncate">{project.name}</h3>
                    </div>
                    <StatusBadge status={getProjectStatusBadge(project.status)} text={getProjectStatusLabel(project.status)} size="sm" />
                  </div>

                  {project.description && (
                    <p className="text-[10px] text-muted-foreground line-clamp-2 mb-2">{project.description}</p>
                  )}

                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground mb-2 flex-wrap">
                    {project.end_date && (
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {formatProjectDate(project.end_date)}
                      </span>
                    )}
                    <span className={`${dl.cls}`}>{dl.label}</span>
                  </div>

                  <div className="mb-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] text-muted-foreground">Progreso</span>
                      <span className="text-[10px] font-medium text-foreground tabular-nums">
                        {hasTasks ? `${pct}%` : 'Sin tareas'}
                      </span>
                    </div>
                    <ProgressBar value={pct} height={5} />
                  </div>

                  <div className="pt-2 border-t border-border mt-auto">
                    <span className="text-[10px] text-muted-foreground">Creado: {formatProjectDate(project.created_at)}</span>
                  </div>
                </Link>
              </motion.div>
            );
          })}

          {filteredProjects.length === 0 && (
            <div className="bg-card/30 border border-dashed border-border rounded-[4px] min-h-[152px] p-4 flex items-center justify-center text-center md:col-span-2">
              <div>
                <p className="text-[12px] font-medium text-foreground">Sin proyectos para mostrar</p>
                <p className="text-[11px] text-muted-foreground mt-1">No hay proyectos con los filtros actuales.</p>
              </div>
            </div>
          )}
        </div>
      )}

      {!isLoadingPage && filteredProjects.length > 0 && totalPages > 1 && (
        <div className="flex items-center justify-between gap-3 bg-card border border-border rounded-[4px] px-4 py-3">
          <p className="text-[11px] text-muted-foreground">
            Mostrando {currentPage * PROJECTS_BATCH_SIZE + 1}-{Math.min((currentPage + 1) * PROJECTS_BATCH_SIZE, filteredProjects.length)} de {filteredProjects.length} proyectos
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setCurrentPage((page) => Math.max(0, page - 1))}
              disabled={currentPage === 0}
              className="h-7 px-3 border border-border rounded-[3px] text-[11px] font-medium text-foreground hover:bg-surface-secondary transition-colors disabled:opacity-50"
            >
              Anterior
            </button>
            <span className="text-[11px] text-muted-foreground">
              Página {currentPage + 1} de {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setCurrentPage((page) => Math.min(totalPages - 1, page + 1))}
              disabled={currentPage >= totalPages - 1}
              className="h-7 px-3 border border-border rounded-[3px] text-[11px] font-medium text-foreground hover:bg-surface-secondary transition-colors disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
          <div className="bg-card border border-border rounded-[4px] p-5 max-w-lg w-full max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[13px] font-semibold text-foreground">Nuevo Proyecto</h2>
              <button onClick={() => setShowCreateModal(false)} className="inline-flex h-8 items-center justify-center rounded-[4px] border border-border bg-card px-3 text-[11px] font-medium text-foreground shadow-sm transition-colors hover:bg-surface-secondary">
                <X className="mr-1 w-3.5 h-3.5" /> Cerrar
              </button>
            </div>

            <form className="space-y-3" onSubmit={handleCreate}>
              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">Nombre *</label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Ej: CRM Implementation"
                  className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">Descripción</label>
                <textarea
                  rows={3}
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="Objetivo y alcance del proyecto"
                  className="w-full bg-surface-secondary border border-border rounded-[3px] px-2.5 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20 resize-none"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-foreground mb-1">Fecha de entrega</label>
                <DatePickerField
                  value={formEnd}
                  onChange={setFormEnd}
                  minDate={tomorrowDate}
                  placeholder="Selecciona la fecha de entrega"
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 h-7 border border-border rounded-[3px] text-[11px] font-medium text-foreground hover:bg-surface-secondary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 h-7 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-50"
                >
                  {creating ? 'Creando…' : 'Crear'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
