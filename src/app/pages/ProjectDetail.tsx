import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import {
  ArrowLeft, Calendar, Users, Clock, CheckCircle2,
  AlertTriangle, UserPlus, RefreshCw, List, Trash2, Settings2,
} from 'lucide-react';
import { motion } from 'motion/react';
import { StatusBadge } from '../components/StatusBadge';
import { DatePickerField } from '../components/DatePickerField';
import { KPICard } from '../components/KPICard';
import { CommandBar } from '../components/CommandBar';
import { ADOTabs } from '../components/ADOTabs';
import { AvatarGroup } from '../components/AvatarGroup';
import { ProgressBar } from '../components/ProgressBar';
import { AssignResponsibleModal, type AssignCandidate } from '../components/AssignResponsibleModal';
import { AddMemberModal } from '../components/AddMemberModal';
import {
  useApiBoards, useApiProjectMembers, useApiUsers, useApiTasks, useApiRoles, useApiSprints,
} from '../hooks/useProjectData';
import { projectsService, tasksService, usersService } from '../../services';
import type { ApiProject, ApiTask, ApiTaskAssignment, ApiUserAccount } from '../../services';
import { useAuth } from '../context/AuthContext';
import { GitHubReposView } from '../components/GitHubReposView';
import { CodeReviewPanel } from '../components/CodeReviewPanel';
import { ProjectTasksWorkspace } from '../components/ProjectTasksWorkspace.tsx';
import { getProjectStatusApiValue, getProjectStatusBadge, getProjectStatusLabel, normalizeProjectStatus, PROJECT_STATUS_OPTIONS } from '../utils/projectStatus';
import { formatProjectDate, getProjectTimeRemainingLabel } from '../utils/projectDates';
import {
  canEditMemberProjectRole,
  getAllowedProjectRoleIdsForUser,
  getProjectCapabilities,
  getProjectRoleIds,
  getUserGithubConnectionState,
  isStakeholderSystemUser,
} from '../utils/projectPermissions';

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const projectId = Number(id) || 0;

  // ── Project ──────────────────────────────────────────────────────────────
  const [project, setProject] = useState<ApiProject | null>(null);
  const [loadingProject, setLoadingProject] = useState(true);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [savingProjectConfig, setSavingProjectConfig] = useState(false);
  const [deletingProject, setDeletingProject] = useState(false);
  const [projectStatus, setProjectStatus] = useState('planning');
  const [projectEndDate, setProjectEndDate] = useState('');

  useEffect(() => {
    if (!projectId) return;
    setLoadingProject(true);
    setProjectError(null);
    projectsService.get(projectId)
      .then(setProject)
      .catch(() => setProjectError('No se pudo cargar el proyecto.'))
      .finally(() => setLoadingProject(false));
  }, [projectId]);

  useEffect(() => {
    setProjectStatus(normalizeProjectStatus(project?.status) ?? 'planning');
    setProjectEndDate(project?.end_date ?? '');
  }, [project?.status, project?.end_date]);

  // ── Boards ───────────────────────────────────────────────────────────────
  const { data: boards, loading: loadingBoards, refetch: refetchBoards } = useApiBoards(projectId);
  const [selectedBoardId, setSelectedBoardId] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (boards && boards.length > 0 && !selectedBoardId) {
      setSelectedBoardId(boards[0].id_board);
    }
  }, [boards, selectedBoardId]);
  // ── Sprints (for project end date validation) ─────────────────────────────
  const { data: sprints } = useApiSprints(projectId);
  const latestSprintEndDate = useMemo(() => {
    const dates = (sprints ?? [])
      .map((s) => s.end_date)
      .filter((d): d is string => d != null)
      .sort();
    return dates.length > 0 ? dates[dates.length - 1] : null;
  }, [sprints]);
  // ── Tasks ─────────────────────────────────────────────────────────────────
  const { statuses, refetch: refetchTasks } = useApiTasks(selectedBoardId, projectId);
  const { data: allProjectTasks } = useApiTasks(undefined, projectId);

  // ── Members + Users ───────────────────────────────────────────────────────
  const { data: members, loading: loadingMembers, refetch: refetchMembers } = useApiProjectMembers(projectId);
  const { data: users, loading: loadingUsers } = useApiUsers();
  const { data: roles } = useApiRoles();

  const currentUserId = Number(user?.id ?? 0);
  const currentUserAccount = useMemo(
    () => (users ?? []).find((candidate) => candidate.id_user === currentUserId) ?? null,
    [users, currentUserId],
  );
  const currentUserMember = useMemo(
    () => (members ?? []).find((member) => member.user === currentUserId) ?? null,
    [members, currentUserId],
  );
  const projectRoleIds = useMemo(() => getProjectRoleIds(roles), [roles]);
  const capabilities = useMemo(
    () => getProjectCapabilities(currentUserMember, currentUserAccount, projectRoleIds),
    [currentUserAccount, currentUserMember, projectRoleIds],
  );
  const canAccessProject = capabilities.canAccessProject;
  const canManageProject = capabilities.canManageProject;
  const canManageMembers = capabilities.canManageMembers;
  const canEditMemberRoles = capabilities.canEditMemberRoles;
  const canManageTasks = capabilities.canManageTasks;
  const canCreateRepos = capabilities.canCreateRepos;

  const candidatesToAdd = useMemo(() => {
    if (!users) return [];
    const memberIds = new Set((members ?? []).map((m) => m.user));
    return users.filter((u) => !memberIds.has(u.id_user));
  }, [users, members]);

  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [bypassGithubCheck, setBypassGithubCheck] = useState(false);
  const handleAddMember = async (userId: number, roleId: number | null) => {
    if (!canManageMembers) {
      throw new Error('Solo el Project Manager puede agregar miembros.');
    }
    const selectedUser = (users ?? []).find((candidate) => candidate.id_user === userId) ?? null;
    const allowedRoleIds = getAllowedProjectRoleIdsForUser(selectedUser, projectRoleIds);
    const githubState = getUserGithubConnectionState(selectedUser);

    if (roleId == null) {
      throw new Error('Debes seleccionar un rol antes de agregar a la persona.');
    }
    if (!allowedRoleIds.includes(roleId)) {
      throw new Error(isStakeholderSystemUser(selectedUser)
        ? 'Los Stakeholders solo pueden entrar con rol Stakeholder.'
        : 'Debes asignar Product Owner, Scrum Master o Developer.');
    }
    if (!bypassGithubCheck && !isStakeholderSystemUser(selectedUser) && githubState.connected !== true) {
      throw new Error('No puedes agregar a esta persona porque GitHub no esta conectado o no se pudo verificar.');
    }
    try {
      await usersService.addMember(projectId, userId, roleId ?? undefined);
      toast.success('Miembro agregado');
      refetchMembers();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo agregar el miembro';
      toast.error(msg);
      throw err;
    }
  };

  const userMap = useMemo(() => {
    const m = new Map<number, string>();
    (users ?? []).forEach((u) => m.set(u.id_user, u.username));
    return m;
  }, [users]);

  const roleMap = useMemo(() => {
    const m = new Map<number, string>();
    (roles ?? []).forEach((r) => m.set(r.id_role, r.name));
    return m;
  }, [roles]);

  const projectRoleOptions = useMemo(
    () => (roles ?? []).filter((role) => getAllowedProjectRoleIdsForUser(null, projectRoleIds).includes(role.id_role) || role.id_role === projectRoleIds.stakeholderId),
    [projectRoleIds, roles],
  );

  const memberUserMap = useMemo(() => {
    const nextMap = new Map<number, ApiUserAccount>();
    (users ?? []).forEach((candidate) => nextMap.set(candidate.id_user, candidate));
    return nextMap;
  }, [users]);

  const doneStatusIds = useMemo(() => {
    const normalizedDoneNames = new Set(['done', 'completada', 'completado']);
    return new Set(
      statuses
        .filter((s) => normalizedDoneNames.has(s.name.trim().toLowerCase()))
        .map((s) => s.id_status),
    );
  }, [statuses]);

  // ── KPIs ──────────────────────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const tList = allProjectTasks ?? [];
    const now = new Date();
    const total = tList.length;
    const completed = tList.filter((t) => t.completed_at != null || (t.status != null && doneStatusIds.has(t.status))).length;
    const overdue = tList.filter(
      (t) => !t.completed_at && (t.status == null || !doneStatusIds.has(t.status)) && t.due_date && new Date(t.due_date) < now,
    ).length;
    const memberCount = (members ?? []).length;
    return { total, completed, overdue, memberCount };
  }, [allProjectTasks, members, doneStatusIds]);

  // ── Days remaining ───────────────────────────────────────────────────────
  const timeRemainingLabel = getProjectTimeRemainingLabel(project?.end_date ?? null, project?.status).label;
  const tomorrowDate = useMemo(() => {
    const next = new Date();
    next.setDate(next.getDate() + 1);
    return next.toISOString().slice(0, 10);
  }, []);
  const hasProjectConfigChanges = projectStatus !== (normalizeProjectStatus(project?.status) ?? 'planning') || projectEndDate !== (project?.end_date ?? '');

  // ── Assign modal ─────────────────────────────────────────────────────────
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assigningResponsible, setAssigningResponsible] = useState(false);
  const currentProjectManagerMember = useMemo(
    () => (members ?? []).find((member) => member.role === projectRoleIds.projectManagerId) ?? null,
    [members, projectRoleIds.projectManagerId],
  );
  const assignCandidates: AssignCandidate[] = useMemo(
    () => (members ?? []).map((m) => ({
      id: m.user,
      name: userMap.get(m.user) ?? `Usuario #${m.user}`,
      email: `user${m.user}@platform`,
      role: roleMap.get(m.role ?? 0) ?? 'Sin rol',
    })),
    [members, userMap, roleMap],
  );
  const handleAssign = async (userId: number) => {
    if (!canManageProject) {
      toast.error('No tienes permisos para reasignar al responsable del proyecto.');
      return;
    }

    const nextResponsibleMember = (members ?? []).find((member) => member.user === userId);
    if (!nextResponsibleMember) {
      toast.error('La persona seleccionada no pertenece al proyecto.');
      return;
    }

    if (currentProjectManagerMember?.user === userId) {
      setShowAssignModal(false);
      return;
    }

    setAssigningResponsible(true);
    try {
      await usersService.updateMember(nextResponsibleMember.id, { role: projectRoleIds.projectManagerId ?? undefined });

      if (currentProjectManagerMember) {
        await usersService.updateMember(currentProjectManagerMember.id, {
          role: projectRoleIds.developerId ?? undefined,
        });
      }

      await refetchMembers();
      const candidate = assignCandidates.find((x) => x.id === userId);
      if (candidate) toast.success(`Responsable asignado: ${candidate.name}`);
      setShowAssignModal(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo reasignar al responsable.';
      toast.error(msg);
    } finally {
      setAssigningResponsible(false);
    }
  };

  const [removingMemberId, setRemovingMemberId] = useState<number | null>(null);
  const [updatingMemberRoleId, setUpdatingMemberRoleId] = useState<number | null>(null);
  const [editingMemberId, setEditingMemberId] = useState<number | null>(null);
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);

  const handleMemberRoleChange = async (memberId: number, nextRoleId: number) => {
    if (!canEditMemberRoles) {
      toast.error('Solo el Project Manager puede cambiar roles del proyecto.');
      return;
    }

    const member = (members ?? []).find((entry) => entry.id === memberId) ?? null;
    const memberUser = member ? memberUserMap.get(member.user) ?? null : null;
    const allowedRoleIds = getAllowedProjectRoleIdsForUser(memberUser, projectRoleIds);

    if (!member) {
      toast.error('No se encontró el miembro seleccionado.');
      return;
    }
    if (!canEditMemberProjectRole(memberUser, member, projectRoleIds)) {
      toast.error('Ese rol no se puede cambiar desde el proyecto.');
      return;
    }
    if (!allowedRoleIds.includes(nextRoleId)) {
      toast.error('Ese cambio de rol no está permitido.');
      return;
    }
    if (member.role === nextRoleId) {
      return;
    }

    setUpdatingMemberRoleId(memberId);
    try {
      await usersService.updateMember(memberId, { role: nextRoleId });
      await refetchMembers();
      toast.success('Rol del miembro actualizado.');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo actualizar el rol del miembro.';
      toast.error(msg);
    } finally {
      setUpdatingMemberRoleId(null);
    }
  };

  const handleRemoveMember = async (memberId: number) => {
    if (!canManageMembers) {
      toast.error('Solo el Project Manager puede eliminar miembros del proyecto.');
      return;
    }

    const member = (members ?? []).find((m) => m.id === memberId);
    if (!member) {
      toast.error('No se encontró el miembro seleccionado.');
      return;
    }

    if (member.role === projectRoleIds.projectManagerId) {
      toast.error('Reasigna primero al responsable del proyecto.');
      return;
    }

    if (!confirm('¿Eliminar este miembro del proyecto?')) {
      return;
    }

    setRemovingMemberId(memberId);
    try {
      const projectTasks = await tasksService.list(undefined, projectId);
      const allAssignments = (await Promise.all(
        projectTasks.map((task: ApiTask) => tasksService.listAssignments(task.id_task)),
      )).flat();
      const projectTaskIds = new Set(projectTasks.map((task: ApiTask) => task.id_task));
      const memberAssignments = allAssignments.filter(
        (assignment: ApiTaskAssignment) => projectTaskIds.has(assignment.task) && assignment.assigned_to === member.user,
      );

      if (memberAssignments.length > 0) {
        await Promise.all(memberAssignments.map((assignment: ApiTaskAssignment) => tasksService.deleteAssignment(assignment.id_assignment)));
      }

      const remainingAssignmentsByTask = allAssignments
        .filter((assignment: ApiTaskAssignment) => projectTaskIds.has(assignment.task) && assignment.assigned_to !== member.user)
        .reduce<Map<number, number[]>>((map: Map<number, number[]>, assignment: ApiTaskAssignment) => {
          const current = map.get(assignment.task) ?? [];
          current.push(assignment.assigned_to);
          map.set(assignment.task, current);
          return map;
        }, new Map());

      const legacyTasksToUpdate = projectTasks.filter((task: ApiTask) => task.assigned_to === member.user);
      if (legacyTasksToUpdate.length > 0) {
        await Promise.all(
          legacyTasksToUpdate.map((task: ApiTask) => tasksService.update(task.id_task, {
            assigned_to: remainingAssignmentsByTask.get(task.id_task)?.[0] ?? null,
          })),
        );
      }

      await usersService.removeMember(memberId);
      await refetchMembers();
      toast.success('Miembro eliminado del proyecto.');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo eliminar el miembro.';
      toast.error(msg);
    } finally {
      setRemovingMemberId(null);
    }
  };

  const handleProjectStatusSave = async () => {
    if (!project) return;
    if (latestSprintEndDate && projectEndDate && projectEndDate < latestSprintEndDate) {
      toast.error(`La fecha de entrega no puede ser antes del fin del último sprint (${latestSprintEndDate}).`);
      return;
    }
    const apiStatus = getProjectStatusApiValue(projectStatus);
    if (!apiStatus) {
      toast.error('Estado de proyecto inválido.');
      return;
    }
    setSavingProjectConfig(true);
    try {
      const updated = await projectsService.update(project.id_project, {
        status: apiStatus,
        end_date: projectEndDate || undefined,
      });
      setProject(updated);
      toast.success('Configuración del proyecto actualizada.');
    } catch {
      toast.error('No se pudo actualizar la configuración del proyecto.');
    } finally {
      setSavingProjectConfig(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!project) return;
    if (!confirm(`¿Eliminar el proyecto "${project.name}"? Esta acción no se puede deshacer.`)) {
      return;
    }

    setDeletingProject(true);
    try {
      await projectsService.delete(project.id_project);
      toast.success('Proyecto eliminado.');
      navigate('/projects');
    } catch {
      toast.error('No se pudo eliminar el proyecto.');
      setDeletingProject(false);
    }
  };

  // ── Tabs ─────────────────────────────────────────────────────────────────
  const initialQueryTab = searchParams.get('tab');
  const initialQueryTaskId = Number(searchParams.get('task'));
  const normalizedInitialTaskId = Number.isNaN(initialQueryTaskId) || initialQueryTaskId <= 0 ? null : initialQueryTaskId;

  type ProjectWorkspaceTab = 'backlog' | 'sprints' | 'boards' | 'milestones';

  const [activeTab, setActiveTab] = useState<'resumen' | ProjectWorkspaceTab | 'code-review' | 'repositorios' | 'equipo' | 'configuracion'>(() => {
    if (initialQueryTab === 'tareas') return 'backlog';
    if (initialQueryTab === 'backlog') return 'backlog';
    if (initialQueryTab === 'sprints') return 'sprints';
    if (initialQueryTab === 'boards') return 'boards';
    if (initialQueryTab === 'milestones') return 'milestones';
    if (initialQueryTab === 'configuracion') return 'configuracion';
    return 'resumen';
  });
  const [initialTaskId, setInitialTaskId] = useState<number | null>(
    initialQueryTab === 'tareas' || initialQueryTab === 'backlog' || initialQueryTab === 'sprints' || initialQueryTab === 'boards' || initialQueryTab === 'milestones'
      ? normalizedInitialTaskId
      : null,
  );

  useEffect(() => {
    const tab = searchParams.get('tab');
    const taskId = Number(searchParams.get('task'));
    const normalizedTaskId = Number.isNaN(taskId) || taskId <= 0 ? null : taskId;

    if (tab === 'tareas' || tab === 'backlog' || tab === 'sprints' || tab === 'boards' || tab === 'milestones') {
      setActiveTab(tab === 'tareas' ? 'backlog' : tab);
      setInitialTaskId(normalizedTaskId);
      return;
    }

    if (tab === 'configuracion') {
      setActiveTab('configuracion');
    }
  }, [searchParams]);

  useEffect(() => {
    if (!canManageProject && activeTab === 'configuracion') {
      setActiveTab('resumen');
    }
  }, [canManageProject, activeTab]);

  const loading = loadingProject || loadingBoards;

  // ── Error state ───────────────────────────────────────────────────────────
  if (projectError) {
    return (
      <div className="px-4 pt-10 text-center">
        <AlertTriangle className="w-8 h-8 text-destructive mx-auto mb-2" />
        <p className="text-[13px] text-destructive">{projectError}</p>
        <button onClick={() => navigate('/projects')} className="mt-3 text-[12px] text-primary hover:underline">
          Volver a Proyectos
        </button>
      </div>
    );
  }

  if (!loadingProject && !loadingMembers && !canAccessProject) {
    return (
      <div className="px-4 pt-10 text-center">
        <AlertTriangle className="w-8 h-8 text-destructive mx-auto mb-2" />
        <p className="text-[13px] text-destructive">No tienes acceso a este proyecto.</p>
        <button onClick={() => navigate('/projects')} className="mt-3 text-[12px] text-primary hover:underline">
          Volver a Proyectos
        </button>
      </div>
    );
  }

  return (
    <div className="px-4 pb-6 pt-3 max-w-[1400px] min-h-full flex flex-col gap-3">
      <section className="rounded-[6px] border border-border bg-card overflow-hidden">
        <CommandBar
          actions={[
            { label: 'Volver', icon: <ArrowLeft className="w-3.5 h-3.5" />, onClick: () => navigate('/projects') },
            { label: 'Actualizar', icon: <RefreshCw className="w-3.5 h-3.5" />, onClick: () => { refetchTasks(); refetchMembers(); refetchBoards(); } },
            ...(canManageProject ? [{ label: 'Asignar responsable', icon: <UserPlus className="w-3.5 h-3.5" />, onClick: () => setShowAssignModal(true) }] : []),
          ]}
          rightSlot={project ? <StatusBadge status={getProjectStatusBadge(project.status)} text={getProjectStatusLabel(project.status)} size="sm" /> : null}
        />

        {loading ? (
          <div className="mx-4 my-3 h-14 animate-pulse bg-surface-secondary/50 rounded-[4px]" />
        ) : project ? (
          <div className="px-4 pb-3 pt-2 border-b border-border">
            <h1 className="text-[16px] font-semibold text-foreground">{project.name}</h1>
            {project.description && (
              <p className="text-[12px] text-muted-foreground mt-0.5 line-clamp-2">{project.description}</p>
            )}
            <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />Inicio: {formatProjectDate(project.created_at)}
              </span>
              {project.end_date && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />Fin: {formatProjectDate(project.end_date)}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3" />{kpis.memberCount} miembros
              </span>
            </div>
          </div>
        ) : null}

        <div className="px-3">
          <ADOTabs
            tabs={[
              { id: 'resumen', label: 'Overview' },
              { id: 'backlog', label: 'Backlog' },
              { id: 'sprints', label: 'Sprints' },
              { id: 'boards', label: 'Boards' },
              { id: 'milestones', label: 'Milestones' },
              { id: 'code-review', label: 'Code Review' },
              { id: 'repositorios', label: 'Repositorios' },
              { id: 'equipo', label: 'Equipo', count: (members ?? []).length },
              ...(canManageProject ? [{ id: 'configuracion', label: 'Configuración', icon: <Settings2 className="w-3.5 h-3.5" /> }] : []),
            ]}
            activeTab={activeTab}
            onTabChange={(id) => setActiveTab(id as typeof activeTab)}
          />
        </div>
      </section>

      <motion.div
        key={activeTab}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className={activeTab === 'backlog' || activeTab === 'sprints' || activeTab === 'boards' || activeTab === 'milestones' ? 'flex-1 min-h-0 flex flex-col' : undefined}
      >
        {/* RESUMEN */}
        {activeTab === 'resumen' && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
              {[
                { title: 'Tareas', value: kpis.total, subtitle: 'en todo el proyecto', icon: <List className="w-4 h-4" />, accentColor: 'info' as const },
                { title: 'Completadas', value: kpis.completed, subtitle: 'finalizadas', icon: <CheckCircle2 className="w-4 h-4" />, accentColor: 'success' as const },
                { title: 'Vencidas', value: kpis.overdue, subtitle: 'requieren atención', icon: <AlertTriangle className="w-4 h-4" />, accentColor: 'destructive' as const },
                {
                  title: 'Tiempo Restante',
                  value: timeRemainingLabel,
                  subtitle: formatProjectDate(project?.end_date),
                  icon: <Clock className="w-4 h-4" />,
                  accentColor: 'warning' as const,
                },
              ].map((card, i) => (
                <motion.div
                  key={card.title}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, delay: i * 0.05, ease: 'easeOut' }}
                >
                  <KPICard title={card.title} value={card.value} subtitle={card.subtitle} icon={card.icon} accentColor={card.accentColor} />
                </motion.div>
              ))}
            </div>

            <div className="grid lg:grid-cols-1 gap-3">
              <div className="space-y-3">
              <div className="bg-card border border-border rounded-[4px] p-4">
                <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em] mb-2.5">
                  Información General
                </h2>
                {project ? (
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5">
                    {[
                      { label: 'Estado', value: getProjectStatusLabel(project.status) },
                      { label: 'Creado', value: formatProjectDate(project.created_at) },
                      { label: 'Fecha fin', value: formatProjectDate(project.end_date) },
                      { label: 'Tiempo restante', value: timeRemainingLabel },
                      { label: 'Miembros', value: `${kpis.memberCount} personas` },
                    ].map((item) => (
                      <div key={item.label}>
                        <dt className="text-[10px] text-muted-foreground">{item.label}</dt>
                        <dd className="text-[13px] font-medium text-foreground mt-0.5">{item.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <div className="h-20 animate-pulse bg-secondary rounded" />
                )}
              </div>

              {/* Completion progress bar */}
              {kpis.total > 0 && (
                <div className="bg-card border border-border rounded-[4px] p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">
                      Avance
                    </h2>
                    <span className="text-[12px] font-semibold text-foreground">
                      {Math.round((kpis.completed / kpis.total) * 100)}%
                    </span>
                  </div>
                  <ProgressBar value={Math.round((kpis.completed / kpis.total) * 100)} height={6} />
                  <p className="text-[10px] text-muted-foreground mt-1.5">
                    {kpis.completed} de {kpis.total} tareas completadas
                  </p>
                </div>
              )}
              </div>
            </div>
          </div>
        )}

        {/* WORKSPACE TABS */}
        {(activeTab === 'backlog' || activeTab === 'sprints' || activeTab === 'boards' || activeTab === 'milestones') && (
          <div className="flex-1 min-h-0 flex flex-col">
            <ProjectTasksWorkspace
              projectId={projectId}
              userMap={userMap}
              assignableUsers={(members ?? []).map((m) => ({
                id: m.user,
                name: userMap.get(m.user) ?? `Usuario #${m.user}`,
              }))}
              canCreateTasks={canManageTasks}
              canCreateBoards={canManageTasks}
              canEditTasks={canManageTasks}
              canDeleteTasks={canManageTasks}
              projectEndDate={project?.end_date ?? null}
              forcedTab={activeTab}
              initialTaskId={initialTaskId}
              onInitialTaskHandled={(taskId: number) => {
                setInitialTaskId((current) => (current === taskId ? null : current));
                const nextParams = new URLSearchParams(searchParams);
                nextParams.delete('task');
                setSearchParams(nextParams, { replace: true });
              }}
            />
          </div>
        )}

        {/* CODE REVIEW */}
        {activeTab === 'code-review' && (
          <CodeReviewPanel
            projectId={projectId}
            repoFullName={project?.github_repo_full_name ?? null}
          />
        )}

        {/* REPOSITORIOS */}
        {activeTab === 'repositorios' && (
          <GitHubReposView projectId={projectId} canCreateRepos={canCreateRepos} />
        )}

        {/* EQUIPO */}
        {activeTab === 'equipo' && (
          <div className="bg-card border border-border rounded-[4px] p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">
                  Miembros del Proyecto
                </h2>
                {members && members.length > 0 && (
                  <AvatarGroup
                    users={(members ?? []).map((m) => ({
                      name: userMap.get(m.user) ?? `Usuario #${m.user}`,
                    }))}
                    max={5}
                    size={24}
                  />
                )}
              </div>
              {canManageMembers && (
                <button
                  onClick={() => setShowAddMemberModal(true)}
                  className="flex items-center gap-1.5 text-[11px] font-medium text-primary bg-primary/10 hover:bg-primary/20 px-2.5 py-1 rounded-[3px] transition-colors"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  Agregar Miembro
                </button>
              )}
            </div>

            {(loadingMembers || loadingUsers) ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => <div key={i} className="h-10 animate-pulse bg-secondary rounded" />)}
              </div>
            ) : !members || members.length === 0 ? (
              <p className="text-[12px] text-muted-foreground py-6 text-center">Sin miembros registrados.</p>
            ) : (
              <div className="space-y-0.5">
                {members.map((member) => {
                  const name = userMap.get(member.user) ?? `Usuario #${member.user}`;
                  const roleName = roleMap.get(member.role ?? 0) ?? `Rol #${member.role ?? '—'}`;
                  const memberUser = memberUserMap.get(member.user) ?? null;
                  const canChangeRole = canEditMemberRoles && canEditMemberProjectRole(memberUser, member, projectRoleIds);
                  const roleIsLocked = isStakeholderSystemUser(memberUser);
                  return (
                    <div
                      key={member.id}
                      className="flex items-center justify-between py-2.5 px-3 rounded-[6px] border border-border/60 bg-surface-secondary/20 hover:bg-accent/30 transition-colors"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-full bg-primary/10 text-primary flex items-center justify-center text-[11px] font-medium">
                          {name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="text-[13px] font-medium text-foreground">{name}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <p className="text-[11px] font-medium text-foreground">{member.role ? roleName : 'Sin rol'}</p>
                            {canChangeRole && (
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingMemberId(member.id);
                                  setEditingRoleId(member.role ?? null);
                                }}
                                className="h-6 px-2.5 text-[10px] font-medium text-primary bg-primary/10 hover:bg-primary/20 rounded-[3px] transition-colors"
                              >
                                Editar
                              </button>
                            )}
                            {member.role === projectRoleIds.projectManagerId && (
                              <span className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                                PM
                              </span>
                            )}
                            {roleIsLocked && (
                              <span className="inline-flex items-center rounded-full border border-border bg-surface-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                                Fijo por sistema
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground">
                          desde {member.joined_at.slice(0, 10)}
                        </span>
                        {canManageMembers && member.role !== projectRoleIds.projectManagerId && (
                          <button
                            type="button"
                            onClick={() => handleRemoveMember(member.id)}
                            disabled={removingMemberId === member.id}
                            className="h-7 px-2 text-[10px] font-medium text-destructive border border-destructive/30 rounded-[3px] hover:bg-destructive/10 transition-colors disabled:opacity-50"
                          >
                            {removingMemberId === member.id ? 'Eliminando…' : 'Eliminar'}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === 'configuracion' && (
          <div className="grid lg:grid-cols-[minmax(0,1fr)_320px] gap-3">
            <div className="bg-card border border-border rounded-[4px] p-4">
              <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em] mb-3">
                Configuración del Proyecto
              </h2>

              <div className="space-y-3 max-w-md">
                <div>
                  <label className="block text-[11px] font-medium text-foreground mb-1">Etapa del proyecto</label>
                  <select
                    value={projectStatus}
                    onChange={(e) => setProjectStatus(e.target.value)}
                    disabled={!canManageProject || savingProjectConfig}
                    className="w-full h-8 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary/20 disabled:opacity-60"
                  >
                    {PROJECT_STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-foreground mb-1">Fecha de entrega</label>
                  <DatePickerField
                    value={projectEndDate}
                    onChange={setProjectEndDate}
                    disabled={!canManageProject || savingProjectConfig}
                    minDate={latestSprintEndDate ?? tomorrowDate}
                    placeholder="Selecciona una fecha de entrega"
                  />
                  {latestSprintEndDate && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      No puede ser antes del último sprint: <span className="font-medium">{latestSprintEndDate}</span>
                    </p>
                  )}
                </div>

                <button
                  type="button"
                  onClick={handleProjectStatusSave}
                  disabled={!canManageProject || savingProjectConfig || !hasProjectConfigChanges}
                  className="h-8 px-3 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-50"
                >
                  {savingProjectConfig ? 'Guardando…' : 'Guardar cambios'}
                </button>

                {!canManageProject && (
                  <p className="text-[11px] text-muted-foreground">Solo el Project Manager del proyecto puede modificar la configuración.</p>
                )}
              </div>
            </div>

            <div className="space-y-3">
              <div className="bg-card border border-border rounded-[4px] p-4">
                <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em] mb-1">Restricciones de equipo</h2>
                <p className="text-[11px] text-muted-foreground mb-3">Por defecto solo se pueden agregar miembros con cuenta de GitHub conectada. Puedes desactivar esto temporalmente.</p>
                <button
                  type="button"
                  disabled={!canManageProject}
                  onClick={() => setBypassGithubCheck((prev) => !prev)}
                  className={`inline-flex items-center gap-2 h-8 px-3 rounded-[3px] text-[11px] font-medium border transition-colors disabled:opacity-50 ${
                    bypassGithubCheck
                      ? 'bg-warning/10 border-warning/40 text-warning hover:bg-warning/20'
                      : 'bg-card border-border text-muted-foreground hover:text-foreground hover:bg-accent'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${bypassGithubCheck ? 'bg-warning' : 'bg-muted-foreground/50'}`} />
                  {bypassGithubCheck ? 'Verificación de GitHub desactivada' : 'Requerir GitHub al agregar miembros'}
                </button>
              </div>

              <div className="bg-card border border-destructive/20 rounded-[4px] p-4 h-fit">
              <h2 className="text-[10px] font-medium text-destructive uppercase tracking-[0.06em] mb-2">
                Zona Peligrosa
              </h2>
              <p className="text-[11px] text-muted-foreground mb-3">
                Eliminar este proyecto también removerá su acceso desde la vista principal.
              </p>
              <button
                type="button"
                onClick={handleDeleteProject}
                disabled={!canManageProject || deletingProject}
                className="h-8 px-3 bg-destructive hover:bg-destructive/90 text-white rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {deletingProject ? 'Eliminando…' : 'Eliminar proyecto'}
              </button>
              </div>
            </div>
          </div>
        )}
      </motion.div>

      <AddMemberModal
        open={showAddMemberModal}
        onOpenChange={setShowAddMemberModal}
        candidates={candidatesToAdd}
        roles={projectRoleOptions}
        roleIds={projectRoleIds}
        bypassGithubCheck={bypassGithubCheck}
        onSubmit={handleAddMember}
      />

      <AssignResponsibleModal
        open={showAssignModal}
        onOpenChange={setShowAssignModal}
        candidates={assignCandidates}
        currentResponsibleId={currentProjectManagerMember?.user}
        onAssign={handleAssign}
        loading={assigningResponsible}
        title="Asignar responsable"
      />

      {editingMemberId != null && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
          <div className="bg-card border border-border rounded-[6px] p-5 max-w-sm w-full shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-[13px] font-semibold text-foreground mb-4">Cambiar rol del miembro</h2>
            {(() => {
              const member = (members ?? []).find((m) => m.id === editingMemberId);
              if (!member) return null;
              const memberUser = memberUserMap.get(member.user);
              const allowedRoleIds = getAllowedProjectRoleIdsForUser(memberUser, projectRoleIds);
              return (
                <div className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-medium text-foreground mb-2">Nuevo rol</label>
                    <select
                      value={editingRoleId ?? ''}
                      onChange={(e) => setEditingRoleId(e.target.value ? Number(e.target.value) : null)}
                      className="w-full h-9 bg-surface-secondary border border-border rounded-[4px] px-3 text-[12px] text-foreground"
                    >
                      {allowedRoleIds.map((roleId) => (
                        <option key={roleId} value={roleId}>{roleMap.get(roleId) ?? `Rol #${roleId}`}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setEditingMemberId(null)}
                      className="flex-1 h-8 border border-border rounded-[3px] text-[11px] font-medium text-foreground hover:bg-accent/30 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        if (editingRoleId != null) {
                          await handleMemberRoleChange(editingMemberId, editingRoleId);
                          setEditingMemberId(null);
                        }
                      }}
                      disabled={updatingMemberRoleId === editingMemberId}
                      className="flex-1 h-8 bg-primary text-primary-foreground rounded-[3px] text-[11px] font-medium hover:bg-primary-hover transition-colors disabled:opacity-50"
                    >
                      {updatingMemberRoleId === editingMemberId ? 'Actualizando…' : 'Guardar'}
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
