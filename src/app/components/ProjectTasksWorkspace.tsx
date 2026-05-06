import { useEffect, useMemo, useState } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  closestCenter,
  useDroppable,
} from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Calendar, Check, Filter, GripVertical, LayoutDashboard, LayoutList, Loader2, Pencil, Plus, Search } from 'lucide-react';
import { toast } from 'sonner';
import {
  useApiBoardColumns,
  useApiBoards,
  useApiMilestones,
  useApiSprints,
  useApiTags,
  useApiTaskAssignments,
  useApiTasks,
} from '../hooks/useProjectData';
import { tasksService } from '../../services';
import type { ApiBoardColumn, ApiTask, ApiTaskPriority } from '../../services';
import { TaskDetailPanel } from './TaskDetailPanel';
import { DatePickerField } from './DatePickerField';
import { TaskAssigneePicker } from './TaskAssigneePicker';
import { TagColorPicker } from './TagColorPicker';

interface ProjectTasksWorkspaceProps {
  projectId: number;
  userMap: Map<number, string>;
  assignableUsers: Array<{ id: number; name: string }>;
  canCreateTasks: boolean;
  canCreateBoards: boolean;
  canEditTasks: boolean;
  canDeleteTasks: boolean;
  projectEndDate?: string | null;
  forcedTab?: WorkspaceTab;
  initialTaskId?: number | null;
  onInitialTaskHandled?: (taskId: number) => void;
}

const TAB_OPTIONS = ['backlog', 'sprints', 'boards', 'milestones'] as const;
export type WorkspaceTab = typeof TAB_OPTIONS[number];

function DroppableColumn({ id, children }: { id: string; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id });
  return <div ref={setNodeRef} className="h-full">{children}</div>;
}

function TaskCard({
  task,
  onOpen,
  draggable,
  tagById,
}: {
  task: ApiTask;
  onOpen: (task: ApiTask) => void;
  draggable: boolean;
  tagById: Map<number, { name: string; color: string }>;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: task.id_task, disabled: !draggable });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      onClick={() => onOpen(task)}
      className="rounded-[4px] border border-border bg-card p-2 text-[11px] cursor-pointer"
    >
      <div className="flex items-start gap-2">
        {draggable && (
          <button type="button" {...attributes} {...listeners} onClick={(e) => e.stopPropagation()} className="mt-0.5">
            <GripVertical className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground truncate">{task.title}</p>
          {task.description && <p className="mt-1 text-muted-foreground line-clamp-2">{task.description}</p>}
          {task.due_date && (
            <div className="mt-2 flex items-center gap-2 text-muted-foreground">
              <span className="inline-flex items-center gap-1"><Calendar className="w-3 h-3" />{task.due_date}</span>
            </div>
          )}
          {task.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1">
              {task.tags.map((tagId) => {
                const tag = tagById.get(tagId);
                return (
                  <span
                    key={tagId}
                    className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-surface-secondary/70 px-2 py-0.5 text-[10px] text-foreground"
                    style={{ boxShadow: `inset 0 0 0 1px ${(tag?.color ?? '#56697f')}33` }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: tag?.color ?? '#56697f' }} />
                    {tag?.name ?? `#${tagId}`}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}



export function ProjectTasksWorkspace({
  projectId,
  userMap,
  assignableUsers,
  canCreateTasks,
  canCreateBoards,
  canEditTasks,
  canDeleteTasks,
  projectEndDate = null,
  forcedTab,
  initialTaskId = null,
  onInitialTaskHandled,
}: ProjectTasksWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(forcedTab ?? 'backlog');
  const [selectedTask, setSelectedTask] = useState<ApiTask | null>(null);
  const [selectedSprintId, setSelectedSprintId] = useState<number | null>(null);
  const [selectedBoardId, setSelectedBoardId] = useState<number | null>(null);
  const [sprintViewMode, setSprintViewMode] = useState<'kanban' | 'list'>('kanban');
  const [activeDragId, setActiveDragId] = useState<number | null>(null);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  const [backlogSearch, setBacklogSearch] = useState('');
  const [showTagFilter, setShowTagFilter] = useState(false);
  const [tagFilterSearch, setTagFilterSearch] = useState('');

  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showBoardModal, setShowBoardModal] = useState(false);
  const [showColumnModal, setShowColumnModal] = useState(false);
  const [showSprintModal, setShowSprintModal] = useState(false);
  const [editingSprint, setEditingSprint] = useState<{ id: number; name: string; start_date: string; end_date: string; status: 'planned' | 'active' | 'closed' } | null>(null);
  const [savingSprintEdit, setSavingSprintEdit] = useState(false);
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [showTagModal, setShowTagModal] = useState(false);

  const [newTask, setNewTask] = useState({
    title: '',
    description: '',
    due_date: '',
    priority: null as number | null,
    tags: [] as number[],
    assignedTo: [] as number[],
    sprint: null as number | null,
  });
  const [newBoard, setNewBoard] = useState({ name: '', description: '' });
  const [newColumn, setNewColumn] = useState({ name: '', is_final: false });
  const [newSprint, setNewSprint] = useState({ name: '', start_date: '', end_date: '', status: 'planned' as 'planned' | 'active' | 'closed' });
  const [newMilestone, setNewMilestone] = useState({ name: '', description: '', due_date: '' });
  const [newTag, setNewTag] = useState({ name: '', color: '#56697f' });

  // State for pushing backlog tasks to a sprint+board
  const [pushingTaskId, setPushingTaskId] = useState<number | null>(null);
  const [pushSprintId, setPushSprintId] = useState<number | null>(null);
  const [pushBoardId, setPushBoardId] = useState<number | null>(null);
  const [pushColumnId, setPushColumnId] = useState<number | null>(null);
  const [savingPush, setSavingPush] = useState(false);

  const { data: tasks, loading: loadingTasks, refetch: refetchTasks, priorities } = useApiTasks(undefined, projectId);
  const { data: boards, loading: loadingBoards, refetch: refetchBoards } = useApiBoards(projectId);
  const { data: columns, loading: loadingColumns, refetch: refetchColumns } = useApiBoardColumns();
  const { data: sprints, loading: loadingSprints, refetch: refetchSprints } = useApiSprints(projectId);
  const { data: milestones, loading: loadingMilestones, refetch: refetchMilestones } = useApiMilestones(projectId);
  const { data: tags, loading: loadingTags, refetch: refetchTags } = useApiTags(projectId);

  const taskIds = useMemo(() => (tasks ?? []).map((task) => task.id_task), [tasks]);
  const { data: taskAssignments, refetch: refetchTaskAssignments } = useApiTaskAssignments(taskIds);

  const loading = loadingTasks || loadingBoards || loadingColumns || loadingSprints || loadingMilestones || loadingTags;

  const boardColumnsByBoard = useMemo(() => {
    const map = new Map<number, ApiBoardColumn[]>();
    (columns ?? []).forEach((column) => {
      const existing = map.get(column.board) ?? [];
      existing.push(column);
      map.set(column.board, existing);
    });
    map.forEach((value, key) => {
      map.set(
        key,
        value.slice().sort((a, b) => {
          if (a.is_final !== b.is_final) return a.is_final ? 1 : -1;
          return a.order - b.order;
        }),
      );
    });
    return map;
  }, [boards, columns]);

  const backlogTasks = useMemo(
    () => (tasks ?? []).filter((task) => task.sprint == null),
    [tasks],
  );

  const selectedBoardColumns = useMemo(
    () => (selectedBoardId ? (boardColumnsByBoard.get(selectedBoardId) ?? []) : []),
    [selectedBoardId, boardColumnsByBoard],
  );

  const tomorrowDate = useMemo(() => {
    const next = new Date();
    next.setDate(next.getDate() + 1);
    return next.toISOString().slice(0, 10);
  }, []);

  // Latest end_date among sprints that have one, used to enforce sequential sprint creation
  const latestSprintEndDate = useMemo(() => {
    const dates = (sprints ?? [])
      .map((s) => s.end_date)
      .filter((d): d is string => d != null)
      .sort();
    return dates.length > 0 ? dates[dates.length - 1] : null;
  }, [sprints]);

  // True when the latest sprint already reaches the project end — no room for more
  const noMoreSprintsAllowed = !!(latestSprintEndDate && projectEndDate && latestSprintEndDate >= projectEndDate);

  // Minimum start date for a new sprint: day AFTER latest sprint end (or tomorrow)
  const sprintStartMinDate = useMemo(() => {
    if (!latestSprintEndDate) return tomorrowDate;
    const d = new Date(latestSprintEndDate);
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  }, [latestSprintEndDate, tomorrowDate]);

  const priorityById = useMemo(() => {
    const map = new Map<number, ApiTaskPriority>();
    priorities.forEach((priority) => map.set(priority.id_priority, priority));
    return map;
  }, [priorities]);

  const defaultBacklogColumnId = useMemo(() => {
    const projectBoardIds = new Set((boards ?? []).map((board) => board.id_board));
    const allColumns = (columns ?? [])
      .filter((column) => projectBoardIds.has(column.board))
      .slice()
      .sort((a, b) => a.order - b.order);
    if (allColumns.length === 0) return null;

    const namedBacklog = allColumns.find((column) => {
      const name = column.name.trim().toLowerCase();
      return name.includes('backlog') || name.includes('to do') || name.includes('todo') || name.includes('por hacer');
    });
    if (namedBacklog) return namedBacklog.id_column;

    const firstNonFinal = allColumns.find((column) => !column.is_final);
    return firstNonFinal?.id_column ?? allColumns[0].id_column;
  }, [columns]);

  const sprintTasks = useMemo(() => {
    const source = (tasks ?? []).filter((task) => selectedSprintId != null && task.sprint === selectedSprintId);
    const withTagFilter = selectedTagIds.length > 0
      ? source.filter((task) => selectedTagIds.every((tagId) => task.tags.includes(tagId)))
      : source;

    if (!selectedBoardId) return withTagFilter;
    const boardColumnIds = new Set((boardColumnsByBoard.get(selectedBoardId) ?? []).map((col) => col.id_column));
    return withTagFilter.filter((task) => boardColumnIds.has(task.board_column));
  }, [tasks, selectedSprintId, selectedTagIds, selectedBoardId, boardColumnsByBoard]);

  const backlogTagFilteredTasks = useMemo(() => {
    let result = backlogTasks;
    if (selectedTagIds.length > 0) result = result.filter((task) => selectedTagIds.every((tagId) => task.tags.includes(tagId)));
    if (backlogSearch.trim()) result = result.filter((task) => task.title.toLowerCase().includes(backlogSearch.trim().toLowerCase()));
    return result;
  }, [backlogTasks, selectedTagIds, backlogSearch]);

  const tagById = useMemo(() => {
    const map = new Map<number, { name: string; color: string }>();
    (tags ?? []).forEach((tag) => {
      map.set(tag.id_tag, { name: tag.name, color: tag.color || '#56697f' });
    });
    return map;
  }, [tags]);

  const filteredTagOptions = useMemo(() => {
    const query = tagFilterSearch.trim().toLowerCase();
    const source = (tags ?? []).filter((tag) => query ? tag.name.toLowerCase().includes(query) : true);
    return source.sort((a, b) => {
      const aSelected = selectedTagIds.includes(a.id_tag) ? 0 : 1;
      const bSelected = selectedTagIds.includes(b.id_tag) ? 0 : 1;
      if (aSelected !== bSelected) return aSelected - bSelected;
      return a.name.localeCompare(b.name, 'es', { sensitivity: 'base' });
    });
  }, [tags, tagFilterSearch, selectedTagIds]);

  useEffect(() => {
    if (!initialTaskId || !tasks) return;
    const target = tasks.find((task) => task.id_task === initialTaskId);
    if (!target) return;
    setSelectedTask(target);
    onInitialTaskHandled?.(initialTaskId);
  }, [initialTaskId, onInitialTaskHandled, tasks]);

  useEffect(() => {
    if (forcedTab) {
      setActiveTab(forcedTab);
    }
  }, [forcedTab]);

  const selectedTaskAssignments = useMemo(() => taskAssignments ?? [], [taskAssignments]);

  const createTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canCreateTasks) {
      toast.error('No tienes permisos para crear tareas.');
      return;
    }

    if (!newTask.title.trim()) {
      toast.error('El titulo es obligatorio.');
      return;
    }

    const boardColumn = defaultBacklogColumnId ?? null;

    if (newTask.priority == null) {
      toast.error('Selecciona una prioridad.');
      return;
    }

    try {
      const created = await tasksService.create({
        project: projectId,
        board_column: boardColumn,
        title: newTask.title.trim(),
        description: newTask.description.trim() || undefined,
        due_date: newTask.due_date || undefined,
        priority: newTask.priority,
        sprint: newTask.sprint,
        milestone: null,
        tags: newTask.tags,
        ...(newTask.assignedTo.length > 0 ? { assigned_to: newTask.assignedTo[0] } : {}),
      });

      await Promise.all(newTask.assignedTo.map((assignedId) => tasksService.createAssignment({ task: created.id_task, assigned_to: assignedId })));

      setShowTaskModal(false);
      setNewTask({
        title: '',
        description: '',
        due_date: '',
        priority: null,
        tags: [],
        assignedTo: [],
        sprint: null,
      });
      refetchTasks();
      refetchTaskAssignments();
      toast.success('Tarea creada.');
    } catch {
      toast.error('No se pudo crear la tarea.');
    }
  };

  const createBoard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBoard.name.trim()) return;
    try {
      const created = await tasksService.createBoard(projectId, newBoard.name.trim(), newBoard.description.trim() || undefined);
      setSelectedBoardId(created.id_board);
      setNewBoard({ name: '', description: '' });
      setShowBoardModal(false);
      refetchBoards();
      toast.success('Board creado.');
    } catch {
      toast.error('No se pudo crear el board.');
    }
  };

  const createColumn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedBoardId || !newColumn.name.trim()) return;
    const nextOrder = (boardColumnsByBoard.get(selectedBoardId) ?? []).length + 1;
    try {
      await tasksService.createBoardColumn({
        board: selectedBoardId,
        name: newColumn.name.trim(),
        order: nextOrder,
        is_final: newColumn.is_final,
      });
      setNewColumn({ name: '', is_final: false });
      setShowColumnModal(false);
      refetchColumns();
      toast.success('Columna creada.');
    } catch {
      toast.error('No se pudo crear la columna.');
    }
  };

  const saveSprintEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingSprint) return;
    if (editingSprint.start_date && editingSprint.end_date && editingSprint.start_date > editingSprint.end_date) {
      toast.error('La fecha de inicio no puede ser posterior a la fecha de fin.');
      return;
    }
    if (projectEndDate && editingSprint.end_date && editingSprint.end_date > projectEndDate) {
      toast.error(`El sprint no puede terminar después del fin del proyecto (${projectEndDate}).`);
      return;
    }
    setSavingSprintEdit(true);
    try {
      await tasksService.updateSprint(editingSprint.id, {
        start_date: editingSprint.start_date || null,
        end_date: editingSprint.end_date || null,
        status: editingSprint.status,
      });
      refetchSprints();
      setEditingSprint(null);
      toast.success('Sprint actualizado.');
    } catch {
      toast.error('No se pudo actualizar el sprint.');
    } finally {
      setSavingSprintEdit(false);
    }
  };

  const handlePushTaskToSprint = async () => {
    if (!pushingTaskId || !pushSprintId) return;
    setSavingPush(true);
    try {
      await tasksService.update(pushingTaskId, {
        sprint: pushSprintId,
        board_column: pushColumnId ?? null,
      });
      refetchTasks();
      setPushingTaskId(null);
      setPushSprintId(null);
      setPushBoardId(null);
      setPushColumnId(null);
      toast.success('Tarea enviada al sprint.');
    } catch {
      toast.error('No se pudo enviar la tarea al sprint.');
    } finally {
      setSavingPush(false);
    }
  };

  const createSprint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSprint.start_date || !newSprint.end_date) {
      toast.error('Las fechas de inicio y fin son obligatorias.');
      return;
    }
    if (latestSprintEndDate && newSprint.start_date <= latestSprintEndDate) {
      toast.error(`El sprint debe iniciar después del ${latestSprintEndDate} (el día siguiente o más tarde).`);
      return;
    }
    if (projectEndDate && newSprint.end_date > projectEndDate) {
      toast.error(`El sprint no puede terminar después del fin del proyecto (${projectEndDate}).`);
      return;
    }
    if (newSprint.start_date > newSprint.end_date) {
      toast.error('La fecha de inicio no puede ser posterior a la fecha de fin.');
      return;
    }
    const autoName = `Sprint ${(sprints ?? []).length + 1}`;
    try {
      const created = await tasksService.createSprint({
        project: projectId,
        name: autoName,
        start_date: newSprint.start_date || undefined,
        end_date: newSprint.end_date || undefined,
        status: newSprint.status,
      });
      setSelectedSprintId(created.id_sprint);
      setNewSprint({ name: '', start_date: '', end_date: '', status: 'planned' });
      setShowSprintModal(false);
      refetchSprints();
      toast.success('Sprint creado.');
    } catch {
      toast.error('No se pudo crear el sprint.');
    }
  };

  const createMilestone = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMilestone.name.trim()) return;
    try {
      await tasksService.createMilestone({
        project: projectId,
        name: newMilestone.name.trim(),
        description: newMilestone.description.trim() || undefined,
        due_date: newMilestone.due_date || undefined,
      });
      setShowMilestoneModal(false);
      setNewMilestone({ name: '', description: '', due_date: '' });
      refetchMilestones();
      toast.success('Milestone creado.');
    } catch {
      toast.error('No se pudo crear el milestone.');
    }
  };

  const createTag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTag.name.trim()) return;
    try {
      await tasksService.createTag({ project: projectId, name: newTag.name.trim(), color: newTag.color });
      setShowTagModal(false);
      setNewTag({ name: '', color: '#56697f' });
      refetchTags();
      toast.success('Tag creado.');
    } catch {
      toast.error('No se pudo crear el tag.');
    }
  };

  const selectedBoard = (boards ?? []).find((board) => board.id_board === selectedBoardId) ?? null;

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveDragId(null);
    if (!canEditTasks) return;
    const { active, over } = event;
    if (!over) return;
    const draggedTask = (tasks ?? []).find((task) => task.id_task === Number(active.id));
    if (!draggedTask) return;
    let targetColumnId: number | null = null;
    const overId = String(over.id);
    if (overId.startsWith('column-')) {
      targetColumnId = Number(overId.replace('column-', ''));
    } else {
      const overTask = (tasks ?? []).find((task) => String(task.id_task) === overId);
      targetColumnId = overTask?.board_column ?? null;
    }
    if (!targetColumnId || draggedTask.board_column === targetColumnId) return;
    const targetColumn = (columns ?? []).find((column) => column.id_column === targetColumnId);
    try {
      await tasksService.update(draggedTask.id_task, {
        board_column: targetColumnId,
        completed_at: targetColumn?.is_final ? (draggedTask.completed_at ?? new Date().toISOString()) : null,
      });
      refetchTasks();
      toast.success('Tarea movida.');
    } catch {
      toast.error('No se pudo mover la tarea.');
    }
  };

  return (
    <div className="h-full min-h-0 flex flex-col gap-3 overflow-hidden">

      {/* ── Toolbar ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        {/* Left: tab switcher (when not forced) */}
        {!forcedTab && (
          <div className="flex items-center gap-1 rounded-[4px] border border-border bg-surface-secondary/40 p-1 shrink-0">
            {TAB_OPTIONS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`h-7 px-3 rounded-[3px] text-[11px] font-medium capitalize ${activeTab === tab ? 'bg-card text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              >
                {tab}
              </button>
            ))}
          </div>
        )}

        {/* Left: search + filter (backlog only) */}
        {activeTab === 'backlog' && (
          <>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
              <input
                value={backlogSearch}
                onChange={(e) => setBacklogSearch(e.target.value)}
                placeholder="Buscar tarea…"
                className="h-8 w-48 rounded-[3px] border border-border bg-surface-secondary pl-7 pr-2 text-[11px] placeholder:text-muted-foreground/60"
              />
            </div>
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowTagFilter((v) => !v)}
                className={`h-8 px-2.5 rounded-[3px] border text-[11px] inline-flex items-center gap-1.5 transition-colors ${
                  selectedTagIds.length > 0
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground'
                }`}
              >
                <Filter className="w-3.5 h-3.5" />
                Filtrar
                {selectedTagIds.length > 0 && (
                  <span className="ml-0.5 inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary text-primary-foreground text-[10px] font-bold">
                    {selectedTagIds.length}
                  </span>
                )}
              </button>
              {showTagFilter && (
                <div className="absolute left-0 top-full mt-1 z-20 rounded-[8px] border border-border bg-card shadow-md p-2.5 w-[320px] flex flex-col gap-2">
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                    <input
                      value={tagFilterSearch}
                      onChange={(e) => setTagFilterSearch(e.target.value)}
                      placeholder="Buscar tags..."
                      className="h-7 w-full rounded-[4px] border border-border bg-surface-secondary pl-7 pr-2 text-[11px] placeholder:text-muted-foreground/60"
                    />
                  </div>

                  {(tags ?? []).length === 0 ? (
                    <span className="text-[10px] text-muted-foreground px-1 py-1">Sin tags en este proyecto</span>
                  ) : filteredTagOptions.length === 0 ? (
                    <span className="text-[10px] text-muted-foreground px-1 py-1">No se encontraron tags</span>
                  ) : (
                    <div className="flex flex-wrap gap-1.5 max-h-[220px] overflow-y-auto pr-0.5">
                      {filteredTagOptions.map((tag) => {
                        const selected = selectedTagIds.includes(tag.id_tag);
                        return (
                          <button
                            key={tag.id_tag}
                            type="button"
                            onClick={() => setSelectedTagIds((current) => selected ? current.filter((id) => id !== tag.id_tag) : [...current, tag.id_tag])}
                            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] transition-colors ${
                              selected
                                ? 'border-primary bg-primary/10 text-primary'
                                : 'border-border bg-surface-secondary/60 text-foreground hover:bg-accent'
                            }`}
                          >
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: tag.color ?? '#56697f' }} />
                            {tag.name}
                            {selected && <Check className="w-3 h-3" />}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {selectedTagIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedTagIds([])}
                      className="mt-0.5 h-7 px-2 rounded-[4px] text-[10px] text-muted-foreground hover:text-foreground border border-border text-left"
                    >
                      Limpiar filtros
                    </button>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right: action buttons */}
        <div className="flex items-center gap-1.5">
          {canCreateBoards && activeTab === 'boards' && (
            <>
              <button
                type="button"
                onClick={() => setShowBoardModal(true)}
                className="h-8 px-3 rounded-[3px] bg-primary text-primary-foreground text-[11px] font-medium inline-flex items-center gap-1.5"
              >
                <LayoutDashboard className="w-3.5 h-3.5" /> Nuevo board
              </button>
              <button
                type="button"
                onClick={() => setShowColumnModal(true)}
                disabled={!selectedBoardId}
                className="h-8 px-3 rounded-[3px] border border-border text-[11px] inline-flex items-center gap-1.5 disabled:opacity-40 hover:bg-accent/30 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" /> Nueva columna
              </button>
            </>
          )}
          {canCreateBoards && activeTab === 'milestones' && (
            <button type="button" onClick={() => setShowMilestoneModal(true)} className="h-8 px-3 rounded-[3px] border border-border text-[11px]">Nuevo milestone</button>
          )}
          {canCreateTasks && activeTab === 'backlog' && (
            <button type="button" onClick={() => { setNewTask((prev) => ({ ...prev, sprint: null })); setShowTaskModal(true); }} className="h-8 px-3 rounded-[3px] bg-primary text-primary-foreground text-[11px] font-medium inline-flex items-center gap-1">
              <Plus className="w-3.5 h-3.5" /> Nueva tarea
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="py-12 flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && activeTab === 'backlog' && (
        <div className="rounded-[4px] border border-border bg-card overflow-auto">
          <table className="w-full min-w-[920px] text-[11px]">
            <thead>
              <tr className="border-b border-border bg-surface-secondary/50">
                <th className="text-left px-4 py-2">Titulo</th>
                <th className="text-left px-4 py-2">Prioridad</th>
                <th className="text-left px-4 py-2">Tags</th>
                {canEditTasks && <th className="text-left px-4 py-2 w-[140px]">Sprint</th>}
              </tr>
            </thead>
            <tbody>
              {backlogTagFilteredTasks.map((task) => (
                <tr key={task.id_task} className="border-b border-border/60 hover:bg-accent/20 cursor-pointer align-top" onClick={() => setSelectedTask(task)}>
                  <td className="px-4 py-3 min-w-[360px]">
                    <p className="text-[12px] font-semibold text-foreground">{task.title}</p>
                    {task.description && <p className="mt-1 text-muted-foreground leading-relaxed">{task.description}</p>}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-[11px] font-medium text-foreground">
                      {priorityById.get(task.priority)?.name ?? `Prioridad ${task.priority}`}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {task.tags.length === 0 ? (
                      <span className="text-[10px] text-muted-foreground">Sin tags</span>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2 max-w-[420px]">
                        {task.tags.slice(0, 4).map((tagId) => {
                          const tag = tagById.get(tagId);
                          const tagName = tag?.name ?? `#${tagId}`;
                          return (
                            <span
                              key={`${task.id_task}-${tagId}`}
                              className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-surface-secondary/70 px-2.5 py-1 text-[10px] font-medium text-foreground"
                              title={tagName}
                              style={{
                                boxShadow: `inset 0 0 0 1px ${(tag?.color ?? '#56697f')}33`,
                              }}
                            >
                              <span
                                className="h-2 w-2 rounded-full shrink-0"
                                style={{ backgroundColor: tag?.color ?? '#56697f' }}
                              />
                              {tagName}
                            </span>
                          );
                        })}
                        {task.tags.length > 4 && (
                          <span className="inline-flex items-center rounded-full border border-border px-2 py-1 text-[10px] text-muted-foreground bg-card">
                            +{task.tags.length - 4}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  {canEditTasks && (
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => {
                          setPushingTaskId(task.id_task);
                          setPushSprintId(null);
                          setPushBoardId(null);
                          setPushColumnId(null);
                        }}
                        className="h-6 px-2 rounded-[3px] border border-dashed border-border text-[10px] text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors inline-flex items-center gap-1"
                      >
                        <Plus className="w-3 h-3" /> Mover
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && activeTab === 'sprints' && (
        <div className="flex-1 min-h-0 flex overflow-hidden rounded-[4px] border border-border bg-card">
          {/* Left: scrollable sprint selector */}
          <div className="w-[210px] flex-shrink-0 border-r border-border flex flex-col">
            <div className="px-3 py-2 border-b border-border flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground font-medium">Sprints</p>
              {canCreateBoards && (
                <button
                  type="button"
                  onClick={() => { setNewSprint((prev) => ({ ...prev, start_date: sprintStartMinDate, end_date: '' })); setShowSprintModal(true); }}
                  disabled={noMoreSprintsAllowed}
                  className="h-6 w-6 rounded-[4px] bg-primary text-primary-foreground shadow-sm hover:opacity-90 transition-opacity inline-flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
                  title={noMoreSprintsAllowed ? 'No hay espacio para más sprints' : 'Nuevo sprint'}
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto">
              {(sprints ?? []).length === 0 ? (
                <p className="px-3 py-4 text-[11px] text-muted-foreground">Sin sprints creados</p>
              ) : (
                (sprints ?? []).map((sprint) => (
                  <button
                    key={sprint.id_sprint}
                    type="button"
                    onClick={() => { setSelectedSprintId(sprint.id_sprint); const firstBoard = (boards ?? [])[0] ?? null; setSelectedBoardId(firstBoard ? firstBoard.id_board : null); }}
                    className={`w-full text-left px-3 py-2.5 border-b border-border/40 last:border-0 transition-colors group ${
                      selectedSprintId === sprint.id_sprint
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-accent/20 text-foreground'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <p className="text-[11px] font-medium truncate">{sprint.name}</p>
                      {canCreateBoards && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingSprint({ id: sprint.id_sprint, name: sprint.name, start_date: sprint.start_date ?? '', end_date: sprint.end_date ?? '', status: sprint.status });
                          }}
                          className="opacity-0 group-hover:opacity-100 h-5 w-5 rounded-[3px] border border-border bg-card text-muted-foreground hover:text-foreground inline-flex items-center justify-center shrink-0 transition-opacity"
                          title="Editar sprint"
                        >
                          <Pencil className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                        sprint.status === 'active' ? 'bg-success/20 text-success' :
                        sprint.status === 'closed' ? 'bg-muted text-muted-foreground' :
                        'bg-amber-500/20 text-amber-600 dark:text-amber-400'
                      }`}>
                        {sprint.status === 'active' ? 'Activo' : sprint.status === 'closed' ? 'Cerrado' : 'Planeado'}
                      </span>
                      {sprint.end_date && (
                        <span className="text-[9px] text-muted-foreground truncate">{sprint.end_date}</span>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Right: sprint content */}
          <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
            {selectedSprintId == null ? (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-[12px] text-muted-foreground">Selecciona un sprint para ver las tareas</p>
              </div>
            ) : (
              <>
                {/* Inner toolbar */}
                <div className="flex items-center gap-2 px-3 py-2 border-b border-border flex-wrap">
                  <select
                    value={selectedBoardId ?? ''}
                    onChange={(e) => setSelectedBoardId(e.target.value ? Number(e.target.value) : null)}
                    className="h-7 min-w-[200px] rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]"
                  >
                    <option value="">Todas las tareas</option>
                    {(boards ?? []).map((board) => (
                      <option key={board.id_board} value={board.id_board}>{board.name}</option>
                    ))}
                  </select>
                  <div className="flex-1" />
                  {selectedBoardId != null && (
                    <div className="flex items-center rounded-[3px] border border-border overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setSprintViewMode('kanban')}
                        className={`h-7 px-2 inline-flex items-center ${sprintViewMode === 'kanban' ? 'bg-primary text-primary-foreground' : 'bg-surface-secondary text-muted-foreground hover:text-foreground'}`}
                        title="Vista kanban"
                      >
                        <LayoutDashboard className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setSprintViewMode('list')}
                        className={`h-7 px-2 inline-flex items-center ${sprintViewMode === 'list' ? 'bg-primary text-primary-foreground' : 'bg-surface-secondary text-muted-foreground hover:text-foreground'}`}
                        title="Vista lista"
                      >
                        <LayoutList className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                  {canCreateTasks && (
                    <button
                      type="button"
                      onClick={() => { setNewTask((prev) => ({ ...prev, sprint: selectedSprintId })); setShowTaskModal(true); }}
                      className="h-7 px-2.5 rounded-[3px] bg-primary text-primary-foreground text-[10px] font-medium inline-flex items-center gap-1"
                    >
                      <Plus className="w-3 h-3" /> Nueva tarea
                    </button>
                  )}
                </div>

                {/* Kanban when board selected, list when "Todas las tareas" */}
                <div className="flex-1 min-h-0 p-3 overflow-hidden flex flex-col">
                  {selectedBoardId != null && sprintViewMode === 'kanban' ? (
                    <DndContext
                      collisionDetection={closestCenter}
                      onDragStart={(event) => setActiveDragId(Number(event.active.id))}
                      onDragEnd={handleDragEnd}
                    >
                      <div className="grid gap-3 flex-1 min-h-0" style={{ gridTemplateColumns: `repeat(${Math.max(selectedBoardColumns.length, 1)}, minmax(0, 1fr))` }}>
                        {selectedBoardColumns.map((column) => {
                          const colTasks = sprintTasks.filter((task) => task.board_column === column.id_column);
                          return (
                            <DroppableColumn key={column.id_column} id={`column-${column.id_column}`}>
                              <div className="h-full rounded-[4px] border border-border bg-surface-secondary/40 p-2 flex flex-col min-h-0">
                                <div className="mb-2 flex items-center justify-between">
                                  <p className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">{column.name}</p>
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${column.is_final ? 'bg-success/20 text-success' : 'bg-card text-muted-foreground'}`}>{colTasks.length}</span>
                                </div>
                                <SortableContext items={colTasks.map((task) => task.id_task)} strategy={verticalListSortingStrategy}>
                                  <div className="flex-1 min-h-0 overflow-y-auto space-y-1.5">
                                    {colTasks.map((task) => (
                                      <TaskCard
                                        key={task.id_task}
                                        task={task}
                                        onOpen={setSelectedTask}
                                        draggable={canEditTasks}
                                        tagById={tagById}
                                      />
                                    ))}
                                  </div>
                                </SortableContext>
                              </div>
                            </DroppableColumn>
                          );
                        })}
                      </div>
                      <DragOverlay>
                        {activeDragId ? (
                          <div className="rounded-[4px] border border-primary bg-card p-2 text-[11px] shadow-sm">
                            {(tasks ?? []).find((task) => task.id_task === activeDragId)?.title ?? 'Tarea'}
                          </div>
                        ) : null}
                      </DragOverlay>
                    </DndContext>
                  ) : (
                    <div className="rounded-[4px] border border-border bg-card overflow-auto h-full">
                      <table className="w-full text-[11px]">
                        <thead>
                          <tr className="border-b border-border bg-surface-secondary/50">
                            <th className="text-left px-3 py-2">Titulo</th>
                            <th className="text-left px-3 py-2">Tags</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sprintTasks.length === 0 ? (
                            <tr>
                              <td colSpan={2} className="px-3 py-6 text-center text-muted-foreground">Sin tareas en este sprint</td>
                            </tr>
                          ) : (
                            sprintTasks.map((task) => {
                              const colName = (columns ?? []).find((col) => col.id_column === task.board_column)?.name ?? null;
                              return (
                                <tr key={task.id_task} className="border-b border-border/60 hover:bg-accent/20 cursor-pointer align-middle" onClick={() => setSelectedTask(task)}>
                                  <td className="px-3 py-2.5 min-w-[260px]">
                                    <p className="font-medium text-foreground">{task.title}</p>
                                  </td>
                                  <td className="px-3 py-2.5">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      {colName && (
                                        <span className="inline-flex items-center gap-1 rounded-[3px] border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                                          {colName}
                                        </span>
                                      )}
                                      {task.tags.map((tagId) => {
                                        const tag = tagById.get(tagId);
                                        return (
                                          <span
                                            key={tagId}
                                            className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-surface-secondary/70 px-2 py-0.5 text-[10px] text-foreground"
                                            style={{ boxShadow: `inset 0 0 0 1px ${(tag?.color ?? '#56697f')}33` }}
                                          >
                                            <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: tag?.color ?? '#56697f' }} />
                                            {tag?.name ?? `#${tagId}`}
                                          </span>
                                        );
                                      })}
                                      {!colName && task.tags.length === 0 && (
                                        <span className="text-[10px] text-muted-foreground">Sin tags</span>
                                      )}
                                    </div>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {!loading && activeTab === 'boards' && (
        <div className="grid lg:grid-cols-[260px_minmax(0,1fr)] gap-3 min-h-0 flex-1">
          <div className="rounded-[4px] border border-border bg-card overflow-y-auto">
            <div className="px-3 py-2 border-b border-border">
              <p className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground font-medium">Boards</p>
            </div>
            {(boards ?? []).length === 0 ? (
              <p className="px-3 py-4 text-[11px] text-muted-foreground">Sin boards creados</p>
            ) : (
              <div className="p-1.5 space-y-0.5">
                {(boards ?? []).map((board) => (
                  <button
                    key={board.id_board}
                    type="button"
                    onClick={() => setSelectedBoardId(board.id_board)}
                    className={`w-full text-left rounded-[4px] px-3 py-2 text-[11px] transition-colors ${
                      selectedBoardId === board.id_board
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent/30 text-foreground'
                    }`}
                  >
                    <p className="font-medium">{board.name}</p>
                    {board.description && (
                      <p className={`text-[10px] mt-0.5 ${selectedBoardId === board.id_board ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>{board.description}</p>
                    )}
                    <p className={`text-[9px] mt-1 ${selectedBoardId === board.id_board ? 'text-primary-foreground/60' : 'text-muted-foreground/70'}`}>
                      {(boardColumnsByBoard.get(board.id_board) ?? []).length} columnas
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-[4px] border border-border bg-card p-3 overflow-auto">
            <h3 className="text-[12px] font-medium text-foreground mb-2">{selectedBoard ? selectedBoard.name : 'Selecciona un board'}</h3>
            {selectedBoard && (
              <div className="space-y-2">
                {(boardColumnsByBoard.get(selectedBoard.id_board) ?? []).map((column) => (
                  <div key={column.id_column} className="flex items-center justify-between rounded-[3px] border border-border bg-surface-secondary/40 px-2 py-1.5 text-[11px]">
                    <span>{column.order}. {column.name}</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const boardCols = boardColumnsByBoard.get(column.board) ?? [];
                          const currentFinal = boardCols.find((c) => c.is_final && c.id_column !== column.id_column);
                          const ops: Promise<unknown>[] = [];
                          if (!column.is_final && currentFinal) {
                            ops.push(tasksService.updateBoardColumn(currentFinal.id_column, { is_final: false }));
                          }
                          ops.push(tasksService.updateBoardColumn(column.id_column, { is_final: !column.is_final }));
                          void Promise.all(ops).then(() => refetchColumns());
                        }}
                        className={`h-6 px-2.5 rounded-full border text-[10px] inline-flex items-center gap-1 transition-colors ${
                          column.is_final
                            ? 'border-success/30 bg-success/10 text-success'
                            : 'border-border text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {column.is_final && <Check className="w-3 h-3" />}
                        {column.is_final ? 'Final' : 'Marcar final'}
                      </button>
                      <button type="button" onClick={() => { void tasksService.deleteBoardColumn(column.id_column).then(() => refetchColumns()); }} className="h-6 px-2 rounded-[3px] border border-destructive/30 text-destructive text-[10px]">Eliminar</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {!loading && activeTab === 'milestones' && (
        <div className="rounded-[4px] border border-border bg-card overflow-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-border bg-surface-secondary/50">
                <th className="text-left px-3 py-2">Milestone</th>
                <th className="text-left px-3 py-2">Due Date</th>
                <th className="text-left px-3 py-2">Estado</th>
              </tr>
            </thead>
            <tbody>
              {(milestones ?? []).map((milestone) => (
                <tr key={milestone.id_milestone} className="border-b border-border/60">
                  <td className="px-3 py-2">
                    <p className="font-medium text-foreground">{milestone.name}</p>
                    {milestone.description && <p className="text-muted-foreground">{milestone.description}</p>}
                  </td>
                  <td className="px-3 py-2">{milestone.due_date ?? '—'}</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => {
                        void tasksService.updateMilestone(milestone.id_milestone, { is_completed: !milestone.is_completed }).then(() => refetchMilestones());
                      }}
                      className={`h-7 px-3 rounded-[3px] border text-[10px] ${milestone.is_completed ? 'border-success/30 text-success bg-success/10' : 'border-border text-muted-foreground'}`}
                    >
                      {milestone.is_completed ? (
                        <span className="inline-flex items-center gap-1"><Check className="w-3 h-3" />Completado</span>
                      ) : 'Marcar completo'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showTaskModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={createTask} className="w-full max-w-2xl rounded-[6px] border border-border bg-card p-5 space-y-3">
            <h2 className="text-[13px] font-semibold text-foreground">
              {newTask.sprint != null
                ? `Nueva tarea — ${(sprints ?? []).find((s) => s.id_sprint === newTask.sprint)?.name ?? 'Sprint'}`
                : 'Nueva tarea (Product Backlog)'}
            </h2>
            <input value={newTask.title} onChange={(e) => setNewTask((prev) => ({ ...prev, title: e.target.value }))} placeholder="Titulo" className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]" />
            <textarea value={newTask.description} onChange={(e) => setNewTask((prev) => ({ ...prev, description: e.target.value }))} placeholder="Descripcion" className="w-full rounded-[3px] border border-border bg-surface-secondary px-2 py-1 text-[11px]" rows={3} />

            <div className="grid md:grid-cols-2 gap-2">
              <DatePickerField
                value={newTask.due_date}
                onChange={(value) => setNewTask((prev) => ({ ...prev, due_date: value }))}
                minDate={tomorrowDate}
                maxDate={projectEndDate ?? undefined}
                placeholder="Fecha limite"
              />
              <select
                value={newTask.priority ?? ''}
                onChange={(e) => setNewTask((prev) => ({ ...prev, priority: e.target.value ? Number(e.target.value) : null }))}
                className="h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]"
              >
                <option value="">Selecciona prioridad</option>
                {priorities.map((priority) => (
                  <option key={priority.id_priority} value={priority.id_priority}>{priority.name}</option>
                ))}
              </select>
            </div>

            <p className="text-[10px] text-muted-foreground">
              {newTask.sprint != null
                ? 'La tarea se creará y asignará al sprint seleccionado.'
                : 'Las tareas nuevas se crean siempre en Product Backlog (sin sprint, sin milestone).'}
            </p>

            <div>
              <p className="text-[11px] text-muted-foreground mb-1">Asignar personas</p>
              <TaskAssigneePicker users={assignableUsers} selectedIds={newTask.assignedTo} onChange={(ids) => setNewTask((prev) => ({ ...prev, assignedTo: ids }))} />
            </div>

            {(tags ?? []).length > 0 && (
              <div>
                <p className="text-[11px] text-muted-foreground mb-1">Tags</p>
                <div className="flex items-center gap-2 flex-wrap">
                  {(tags ?? []).map((tag) => {
                    const selected = newTask.tags.includes(tag.id_tag);
                    return (
                      <button
                        key={tag.id_tag}
                        type="button"
                        onClick={() => setNewTask((prev) => ({
                          ...prev,
                          tags: selected ? prev.tags.filter((id) => id !== tag.id_tag) : [...prev.tags, tag.id_tag],
                        }))}
                        className={`h-6 px-2 rounded-full border text-[10px] ${selected ? 'border-primary text-primary bg-primary/10' : 'border-border text-muted-foreground'}`}
                      >
                        {tag.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => { setNewTask((prev) => ({ ...prev, sprint: null })); setShowTaskModal(false); }} className="h-8 px-3 rounded-[3px] border border-border text-[11px]">Cancelar</button>
              <button type="submit" className="h-8 px-3 rounded-[3px] bg-primary text-primary-foreground text-[11px]">Crear</button>
            </div>
          </form>
        </div>
      )}

      {/* Push task to sprint modal */}
      {pushingTaskId != null && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <div className="w-full max-w-sm rounded-[6px] border border-border bg-card p-5 space-y-3">
            <div>
              <h2 className="text-[13px] font-semibold">Mover al sprint</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">Selecciona sprint y board. La tarea se colocará en la primera columna del board.</p>
            </div>
            <select
              value={pushSprintId ?? ''}
              onChange={(e) => { setPushSprintId(e.target.value ? Number(e.target.value) : null); setPushBoardId(null); setPushColumnId(null); }}
              className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]"
            >
              <option value="">Selecciona sprint</option>
              {(sprints ?? []).map((s) => (
                <option key={s.id_sprint} value={s.id_sprint}>{s.name}</option>
              ))}
            </select>
            <select
              value={pushBoardId ?? ''}
              onChange={(e) => {
                const boardId = e.target.value ? Number(e.target.value) : null;
                setPushBoardId(boardId);
                const firstCol = boardId ? (boardColumnsByBoard.get(boardId) ?? [])[0] ?? null : null;
                setPushColumnId(firstCol ? firstCol.id_column : null);
              }}
              className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]"
            >
              <option value="">Selecciona board</option>
              {(boards ?? []).map((b) => (
                <option key={b.id_board} value={b.id_board}>{b.name}</option>
              ))}
            </select>
            {pushBoardId != null && pushColumnId != null && (
              <p className="text-[10px] text-muted-foreground bg-surface-secondary/60 rounded-[3px] px-2.5 py-1.5">
                Columna asignada: <span className="font-medium text-foreground">{(boardColumnsByBoard.get(pushBoardId) ?? []).find((c) => c.id_column === pushColumnId)?.name ?? '—'}</span>
              </p>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setPushingTaskId(null)} className="h-8 px-3 border border-border rounded-[3px] text-[11px]">Cancelar</button>
              <button
                type="button"
                disabled={!pushSprintId || !pushBoardId || savingPush}
                onClick={() => void handlePushTaskToSprint()}
                className="h-8 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px] disabled:opacity-50 inline-flex items-center gap-1"
              >
                {savingPush ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                Mover al sprint
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit sprint modal */}
      {editingSprint && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={saveSprintEdit} className="w-full max-w-md rounded-[6px] border border-border bg-card p-5 space-y-3">
            <div>
              <h2 className="text-[13px] font-semibold">Editar {editingSprint.name}</h2>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <DatePickerField
                value={editingSprint.start_date}
                onChange={(v) => setEditingSprint((prev) => prev ? { ...prev, start_date: v } : null)}
                placeholder="Fecha inicio"
                maxDate={projectEndDate ?? undefined}
              />
              <DatePickerField
                value={editingSprint.end_date}
                onChange={(v) => setEditingSprint((prev) => prev ? { ...prev, end_date: v } : null)}
                placeholder="Fecha fin"
                minDate={editingSprint.start_date || undefined}
                maxDate={projectEndDate ?? undefined}
              />
            </div>
            <select
              value={editingSprint.status}
              onChange={(e) => setEditingSprint((prev) => prev ? { ...prev, status: e.target.value as 'planned' | 'active' | 'closed' } : null)}
              className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]"
            >
              <option value="planned">Planeado</option>
              <option value="active">Activo</option>
              <option value="closed">Cerrado</option>
            </select>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditingSprint(null)} className="h-8 px-3 border border-border rounded-[3px] text-[11px]">Cancelar</button>
              <button type="submit" disabled={savingSprintEdit} className="h-8 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px] disabled:opacity-50">
                {savingSprintEdit ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </form>
        </div>
      )}

      {showBoardModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={createBoard} className="w-full max-w-md rounded-[6px] border border-border bg-card p-5 space-y-3">
            <h2 className="text-[13px] font-semibold">Nuevo board</h2>
            <input value={newBoard.name} onChange={(e) => setNewBoard((prev) => ({ ...prev, name: e.target.value }))} placeholder="Nombre" className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]" />
            <textarea value={newBoard.description} onChange={(e) => setNewBoard((prev) => ({ ...prev, description: e.target.value }))} placeholder="Descripcion" rows={3} className="w-full rounded-[3px] border border-border bg-surface-secondary px-2 py-1 text-[11px]" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowBoardModal(false)} className="h-8 px-3 border border-border rounded-[3px] text-[11px]">Cancelar</button>
              <button type="submit" className="h-8 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px]">Crear</button>
            </div>
          </form>
        </div>
      )}

      {showColumnModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={createColumn} className="w-full max-w-md rounded-[6px] border border-border bg-card p-5 space-y-3">
            <h2 className="text-[13px] font-semibold">Nueva columna</h2>
            <input value={newColumn.name} onChange={(e) => setNewColumn((prev) => ({ ...prev, name: e.target.value }))} placeholder="Nombre" className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]" />
            <button
              type="button"
              onClick={() => setNewColumn((prev) => ({ ...prev, is_final: !prev.is_final }))}
              className={`w-full rounded-[4px] border px-3 py-2 text-left transition-colors ${
                newColumn.is_final
                  ? 'border-success/30 bg-success/10'
                  : 'border-border bg-surface-secondary/40 hover:bg-surface-secondary/70'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-medium text-foreground">Marcar como columna final</p>
                  <p className="text-[10px] text-muted-foreground">Cuando una tarea llega aqui se considera completada.</p>
                </div>
                <span className={`inline-flex h-5 min-w-[40px] items-center rounded-full border px-1 ${newColumn.is_final ? 'border-success bg-success/20 justify-end' : 'border-border bg-card justify-start'}`}>
                  <span className={`h-3 w-3 rounded-full ${newColumn.is_final ? 'bg-success' : 'bg-muted-foreground/40'}`} />
                </span>
              </div>
            </button>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowColumnModal(false)} className="h-8 px-3 border border-border rounded-[3px] text-[11px]">Cancelar</button>
              <button type="submit" className="h-8 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px]">Crear</button>
            </div>
          </form>
        </div>
      )}

      {showSprintModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={createSprint} className="w-full max-w-md rounded-[6px] border border-border bg-card p-5 space-y-3">
            <div>
              <h2 className="text-[13px] font-semibold">Nuevo sprint</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">Se creará como <span className="font-medium text-foreground">Sprint {(sprints ?? []).length + 1}</span></p>
            </div>
            {latestSprintEndDate && (
              <p className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-500/10 rounded-[3px] px-2.5 py-1.5">
                El sprint anterior termina el <strong>{latestSprintEndDate}</strong>. Este sprint debe iniciar el <strong>{sprintStartMinDate}</strong> o después.
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <DatePickerField
                value={newSprint.start_date}
                onChange={(value) => setNewSprint((prev) => ({ ...prev, start_date: value }))}
                placeholder="Fecha inicio"
                minDate={sprintStartMinDate}
                maxDate={projectEndDate ?? undefined}
              />
              <DatePickerField
                value={newSprint.end_date}
                onChange={(value) => setNewSprint((prev) => ({ ...prev, end_date: value }))}
                placeholder="Fecha fin"
                minDate={newSprint.start_date || sprintStartMinDate}
                maxDate={projectEndDate ?? undefined}
              />
            </div>
            <select value={newSprint.status} onChange={(e) => setNewSprint((prev) => ({ ...prev, status: e.target.value as 'planned' | 'active' | 'closed' }))} className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]">
              <option value="planned">Planeado</option>
              <option value="active">Activo</option>
              <option value="closed">Cerrado</option>
            </select>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowSprintModal(false)} className="h-8 px-3 border border-border rounded-[3px] text-[11px]">Cancelar</button>
              <button type="submit" className="h-8 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px]">Crear</button>
            </div>
          </form>
        </div>
      )}

      {showMilestoneModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={createMilestone} className="w-full max-w-md rounded-[6px] border border-border bg-card p-5 space-y-3">
            <h2 className="text-[13px] font-semibold">Nuevo milestone</h2>
            <input value={newMilestone.name} onChange={(e) => setNewMilestone((prev) => ({ ...prev, name: e.target.value }))} placeholder="Nombre" className="w-full h-8 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px]" />
            <textarea value={newMilestone.description} onChange={(e) => setNewMilestone((prev) => ({ ...prev, description: e.target.value }))} placeholder="Descripcion" rows={3} className="w-full rounded-[3px] border border-border bg-surface-secondary px-2 py-1 text-[11px]" />
            <DatePickerField value={newMilestone.due_date} onChange={(value) => setNewMilestone((prev) => ({ ...prev, due_date: value }))} placeholder="Fecha limite" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowMilestoneModal(false)} className="h-8 px-3 border border-border rounded-[3px] text-[11px]">Cancelar</button>
              <button type="submit" className="h-8 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px]">Crear</button>
            </div>
          </form>
        </div>
      )}

      {showTagModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form onSubmit={createTag} className="w-full max-w-sm rounded-[8px] border border-border bg-card overflow-hidden shadow-lg">
            {/* Header */}
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[13px] font-semibold text-foreground">Nuevo tag</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">Define un nombre y un color para el tag.</p>
            </div>

            {/* Body */}
            <div className="px-4 py-4 space-y-4">
              {/* Name section */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-foreground">Nombre</label>
                <input
                  value={newTag.name}
                  onChange={(e) => setNewTag((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="ej. Bug, Feature, Urgente…"
                  className="w-full h-9 rounded-[4px] border border-border bg-surface-secondary px-3 text-[12px] placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/50"
                  autoFocus
                />
              </div>

              {/* Divider */}
              <div className="border-t border-border/60" />

              {/* Color section */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-foreground">Color</label>
                <TagColorPicker
                  value={newTag.color}
                  onChange={(color) => setNewTag((prev) => ({ ...prev, color }))}
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-border bg-surface-secondary/30">
              <button type="button" onClick={() => setShowTagModal(false)} className="h-8 px-3 border border-border rounded-[4px] text-[11px] hover:bg-accent transition-colors">Cancelar</button>
              <button type="submit" disabled={!newTag.name.trim()} className="h-8 px-3 bg-primary text-primary-foreground rounded-[4px] text-[11px] disabled:opacity-40 transition-opacity">Crear tag</button>
            </div>
          </form>
        </div>
      )}

      <TaskDetailPanel
        task={selectedTask}
        statuses={[]}
        priorities={priorities}
        tags={tags ?? []}
        minDueDate={tomorrowDate}
        maxDueDate={projectEndDate ?? undefined}
        userMap={userMap}
        assignableUsers={assignableUsers}
        taskAssignments={selectedTaskAssignments}
        canEditAssignment={canEditTasks}
        canEditTask={canEditTasks}
        canDeleteTask={canDeleteTasks}
        onClose={() => setSelectedTask(null)}

        onDeleteTask={async (taskToDelete) => {
          await tasksService.delete(taskToDelete.id_task);
          setSelectedTask(null);
          refetchTasks();
          refetchTaskAssignments();
        }}
        onTaskUpdated={(updatedTask) => {
          setSelectedTask(updatedTask);
          refetchTasks();
          refetchTaskAssignments();
        }}
        onCreateTag={async (name, color) => {
          const created = await tasksService.createTag({ project: projectId, name, color });
          refetchTags();
          return created;
        }}
      />
    </div>
  );
}
