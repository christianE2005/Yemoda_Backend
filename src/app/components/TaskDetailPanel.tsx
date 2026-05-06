import { useState, useEffect, useMemo } from 'react';
import {
  X, Calendar, User, MessageSquare, AlertTriangle,
  GitCommit, Send, Loader2, Pencil, Trash2, Plus,
} from 'lucide-react';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'motion/react';
import { tasksService } from '../../services';
import type { ApiTask, ApiTaskStatus, ApiTaskPriority, ApiTaskComment, ApiTaskWarning, ApiTaskAssignment, ApiTag } from '../../services';
import { WarningBadge } from './WarningBadge';
import { TaskAssigneePicker } from './TaskAssigneePicker';
import { DatePickerField } from './DatePickerField';
import { TagColorPicker } from './TagColorPicker';
import { useAuth } from '../context/AuthContext';

const DONE_STATUS_NAMES = new Set(['done', 'completada', 'completado']);
const EMPTY_ASSIGNABLE_USERS: Array<{ id: number; name: string }> = [];
const EMPTY_TASK_ASSIGNMENTS: ApiTaskAssignment[] = [];
export const TASK_REOPEN_ID_STORAGE_KEY = 'pip_reopen_task_id';
export const TASK_REOPEN_PATH_STORAGE_KEY = 'pip_reopen_task_path';

function formatCommentTimestamp(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('es-MX', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface TaskDetailPanelProps {
  task: ApiTask | null;
  statuses: ApiTaskStatus[];
  priorities: ApiTaskPriority[];
  tags?: ApiTag[];
  userMap: Map<number, string>;
  minDueDate?: string;
  maxDueDate?: string;
  assignableUsers?: Array<{ id: number; name: string }>;
  taskAssignments?: ApiTaskAssignment[];
  canEditAssignment?: boolean;
  canEditTask?: boolean;
  canDeleteTask?: boolean;
  onClose: () => void;
  onDeleteTask?: (task: ApiTask) => Promise<void>;
  onTaskUpdated?: (updatedTask: ApiTask) => void;
  onCreateTag?: (name: string, color: string) => Promise<ApiTag>;
}

export function TaskDetailPanel({
  task,
  statuses,
  priorities,
  tags = [],
  userMap,
  minDueDate,
  maxDueDate,
  assignableUsers = EMPTY_ASSIGNABLE_USERS,
  taskAssignments = EMPTY_TASK_ASSIGNMENTS,
  canEditAssignment = true,
  canEditTask = true,
  canDeleteTask = false,
  onClose,
  onDeleteTask,
  onTaskUpdated,
  onCreateTag,
}: TaskDetailPanelProps) {
  const { user } = useAuth();
  const currentUserId = useMemo(() => {
    const parsed = Number(user?.id ?? 0);
    return Number.isNaN(parsed) ? null : parsed;
  }, [user]);

  const [comments, setComments] = useState<ApiTaskComment[]>([]);
  const [loadingComments, setLoadingComments] = useState(false);
  const [warnings, setWarnings] = useState<ApiTaskWarning[]>([]);
  const [loadingWarnings, setLoadingWarnings] = useState(false);
  const [newComment, setNewComment] = useState('');
  const [sendingComment, setSendingComment] = useState(false);
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [editingCommentContent, setEditingCommentContent] = useState('');
  const [tagSearch, setTagSearch] = useState('');
  const [savingTagId, setSavingTagId] = useState<number | null>(null);
  const [showNewTagForm, setShowNewTagForm] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#56697f');
  const [creatingTag, setCreatingTag] = useState(false);

  const [isEditingTask, setIsEditingTask] = useState(false);
  const [savingTask, setSavingTask] = useState(false);
  const [deletingTask, setDeletingTask] = useState(false);
  const [deletingWarningId, setDeletingWarningId] = useState<number | null>(null);
  const [taskForm, setTaskForm] = useState({
    title: '',
    description: '',
    status: '',
    priority: '',
    assignedTo: [] as string[],
    dueDate: '',
  });

  const currentTaskAssignments = useMemo(
    () => (task ? taskAssignments.filter((assignment) => assignment.task === task.id_task) : []),
    [task, taskAssignments],
  );

  const doneStatusIds = useMemo(
    () => new Set(statuses.filter((s) => DONE_STATUS_NAMES.has(s.name.trim().toLowerCase())).map((s) => s.id_status)),
    [statuses],
  );

  useEffect(() => {
    if (!task) return;

    setIsEditingTask(false);
    setTaskForm({
      title: task.title,
      description: task.description ?? '',
      status: task.status != null ? String(task.status) : '',
      priority: task.priority != null ? String(task.priority) : '',
      assignedTo: currentTaskAssignments.length > 0
        ? currentTaskAssignments.map((assignment) => String(assignment.assigned_to))
        : task.assigned_to != null ? [String(task.assigned_to)] : [],
      dueDate: task.due_date ?? '',
    });
  }, [task, currentTaskAssignments]);

  useEffect(() => {
    if (!task) return;

    let cancelled = false;
    const targetTaskId = task.id_task;

    setEditingCommentId(null);
    setEditingCommentContent('');
    setNewComment('');
    setComments([]);
    setWarnings([]);
    setLoadingComments(true);
    setLoadingWarnings(true);

    tasksService.listComments(targetTaskId)
      .then((nextComments) => {
        if (!cancelled) setComments(nextComments);
      })
      .catch(() => {
        if (!cancelled) setComments([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingComments(false);
      });

    tasksService.listWarnings({ task_id: targetTaskId, status: 'active' })
      .then((nextWarnings) => {
        if (!cancelled) setWarnings(nextWarnings);
      })
      .catch(() => {
        if (!cancelled) setWarnings([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingWarnings(false);
      });

    return () => {
      cancelled = true;
    };
  }, [task?.id_task]);

  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!task || !newComment.trim()) return;
    setSendingComment(true);
    try {
      const created = await tasksService.addComment(task.id_task, newComment.trim(), currentUserId ?? undefined);
      const createdWithUser = created.user == null && currentUserId != null
        ? { ...created, user: currentUserId }
        : created;
      setComments((prev) => [...prev, createdWithUser]);
      setNewComment('');
      toast.success('Comentario agregado');
    } catch {
      toast.error('Error al agregar comentario');
    } finally {
      setSendingComment(false);
    }
  };

  const handleStartEditComment = (comment: ApiTaskComment) => {
    setEditingCommentId(comment.id_comment);
    setEditingCommentContent(comment.content);
  };

  const handleUpdateComment = async (commentId: number) => {
    if (!editingCommentContent.trim()) return;
    try {
      const updated = await tasksService.updateComment(commentId, { content: editingCommentContent.trim() });
      setComments((prev) => prev.map((c) => (c.id_comment === commentId ? updated : c)));
      setEditingCommentId(null);
      setEditingCommentContent('');
      toast.success('Comentario actualizado');
    } catch {
      toast.error('No se pudo actualizar el comentario (revisa si el backend lo soporta).');
    }
  };

  const handleDeleteComment = async (commentId: number) => {
    if (!window.confirm('¿Eliminar comentario?')) return;
    try {
      await tasksService.deleteComment(commentId);
      setComments((prev) => prev.filter((c) => c.id_comment !== commentId));
      toast.success('Comentario eliminado');
    } catch {
      toast.error('No se pudo eliminar el comentario (revisa si el backend lo soporta).');
    }
  };

  const handleSaveTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canEditTask) {
      toast.error('Tu rol no puede editar historias.');
      return;
    }
    if (!task || !taskForm.title.trim()) return;

    setSavingTask(true);
    try {
      const nextStatusId = taskForm.status ? Number(taskForm.status) : null;
      const shouldSetCompleted = nextStatusId != null && doneStatusIds.has(nextStatusId);
      const updated = await tasksService.update(task.id_task, {
        title: taskForm.title.trim(),
        description: taskForm.description.trim() || null,
        status: nextStatusId,
        priority: taskForm.priority ? Number(taskForm.priority) : null,
        assigned_to: taskForm.assignedTo.length > 0 ? Number(taskForm.assignedTo[0]) : null,
        due_date: taskForm.dueDate || null,
        completed_at: shouldSetCompleted ? (task.completed_at ?? new Date().toISOString()) : null,
      });

      const nextAssignedIds = new Set(taskForm.assignedTo.map((value) => Number(value)));
      const currentAssignedIds = new Set(currentTaskAssignments.map((assignment) => assignment.assigned_to));

      const assignmentsToCreate = Array.from(nextAssignedIds).filter((assignedId) => !currentAssignedIds.has(assignedId));
      const assignmentsToDelete = currentTaskAssignments.filter((assignment) => !nextAssignedIds.has(assignment.assigned_to));

      await Promise.all([
        ...assignmentsToCreate.map((assignedId) => tasksService.createAssignment({ task: task.id_task, assigned_to: assignedId })),
        ...assignmentsToDelete.map((assignment) => tasksService.deleteAssignment(assignment.id_assignment)),
      ]);

      onTaskUpdated?.(updated);
      setIsEditingTask(false);
      toast.success('Historia actualizada');
    } catch {
      toast.error('Error al actualizar la historia');
    } finally {
      setSavingTask(false);
    }
  };

  const handleDeleteTask = async () => {
    if (!task || !onDeleteTask) return;
    if (!canDeleteTask) {
      toast.error('Solo Product Owner o Project Manager pueden eliminar historias.');
      return;
    }

    if (!window.confirm('¿Eliminar esta historia? Esta acción no se puede deshacer.')) {
      return;
    }

    setDeletingTask(true);
    try {
      await onDeleteTask(task);
    } finally {
      setDeletingTask(false);
    }
  };

  const handleDeleteWarning = async (warningId: number) => {
    if (!canEditTask) {
      toast.error('Tu rol no puede eliminar warnings.');
      return;
    }
    if (!window.confirm('¿Eliminar este warning?')) return;

    setDeletingWarningId(warningId);
    try {
      await tasksService.deleteWarning(warningId);
      if (task) {
        sessionStorage.setItem(TASK_REOPEN_ID_STORAGE_KEY, String(task.id_task));
        sessionStorage.setItem(TASK_REOPEN_PATH_STORAGE_KEY, window.location.pathname);
      }
      toast.success('Warning eliminado.');
      window.location.reload();
    } catch {
      toast.error('No se pudo eliminar el warning.');
    } finally {
      setDeletingWarningId(null);
    }
  };

  const handleCreateAndAddTag = async () => {
    if (!onCreateTag || !newTagName.trim() || !task) return;
    setCreatingTag(true);
    try {
      const created = await onCreateTag(newTagName.trim(), newTagColor);
      await handleAddTaskTag(created.id_tag);
      setNewTagName('');
      setNewTagColor('#56697f');
      setShowNewTagForm(false);
      toast.success('Tag creado y asignado.');
    } catch {
      toast.error('No se pudo crear el tag.');
    } finally {
      setCreatingTag(false);
    }
  };

  const handleAddTaskTag = async (tagId: number) => {
    if (!task || !canEditTask) return;
    if (task.tags.includes(tagId)) return;
    setSavingTagId(tagId);
    try {
      const updated = await tasksService.update(task.id_task, {
        tags: [...task.tags, tagId],
      });
      onTaskUpdated?.(updated);
      setTagSearch('');
      toast.success('Tag agregado.');
    } catch {
      toast.error('No se pudo agregar el tag.');
    } finally {
      setSavingTagId(null);
    }
  };

  const handleRemoveTaskTag = async (tagId: number) => {
    if (!task || !canEditTask) return;
    setSavingTagId(tagId);
    try {
      const updated = await tasksService.update(task.id_task, {
        tags: task.tags.filter((id) => id !== tagId),
      });
      onTaskUpdated?.(updated);
      toast.success('Tag removido.');
    } catch {
      toast.error('No se pudo remover el tag.');
    } finally {
      setSavingTagId(null);
    }
  };

  const pr = task ? priorities.find((p) => p.id_priority === task.priority) : null;
  const assignedNames = currentTaskAssignments.length > 0
    ? currentTaskAssignments.map((assignment) => userMap.get(assignment.assigned_to) ?? `#${assignment.assigned_to}`)
    : task?.assigned_to ? [userMap.get(task.assigned_to) ?? `#${task.assigned_to}`] : [];
  const isOverdue = task && !task.completed_at && task.due_date && new Date(task.due_date) < new Date();
  const activeWarnings = warnings.filter((w) => w.status === 'active');
  const showWarningsSidePanel = loadingWarnings || activeWarnings.length > 0;

  const selectedTaskTags = useMemo(() => {
    if (!task) return [] as ApiTag[];
    return tags.filter((tag) => task.tags.includes(tag.id_tag));
  }, [tags, task]);

  const searchableTags = useMemo(() => {
    if (!task) return [] as ApiTag[];
    const query = tagSearch.trim().toLowerCase();
    return tags
      .filter((tag) => !task.tags.includes(tag.id_tag))
      .filter((tag) => (query ? tag.name.toLowerCase().includes(query) : true))
      .slice(0, 8);
  }, [tags, task, tagSearch]);

  return (
    <>
      <AnimatePresence>
        {task && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-30 bg-black/20"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      <div
        className={`fixed top-0 right-0 h-full z-40 transition-all duration-300 ease-in-out ${showWarningsSidePanel ? 'w-[760px]' : 'w-[420px]'} ${
          task ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {task && (
          <div className="h-full flex min-w-0">
            <div className="w-[420px] min-w-0 bg-card border-l border-border flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-secondary/50 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                {pr && (
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em]">
                    {pr.name}
                  </span>
                )}
                {activeWarnings.length > 0 && <WarningBadge count={activeWarnings.length} />}
              </div>
              <div className="flex items-center gap-1.5">
                {!isEditingTask && canEditTask && (
                  <button
                    onClick={() => setIsEditingTask(true)}
                    className="inline-flex items-center gap-1 h-6 px-2 border border-border rounded-[3px] text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    <Pencil className="w-3 h-3" /> Editar
                  </button>
                )}
                <button onClick={onClose} className="p-1 rounded-[3px] hover:bg-surface-secondary transition-colors">
                  <X className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Title & Description */}
              {isEditingTask ? (
                <form onSubmit={handleSaveTask} className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-medium text-foreground mb-1">Titulo</label>
                    <input
                      type="text"
                      required
                      value={taskForm.title}
                      onChange={(e) => setTaskForm((prev) => ({ ...prev, title: e.target.value }))}
                      className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px]"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-foreground mb-1">Descripcion</label>
                    <textarea
                      rows={3}
                      value={taskForm.description}
                      onChange={(e) => setTaskForm((prev) => ({ ...prev, description: e.target.value }))}
                      className="w-full bg-surface-secondary border border-border rounded-[3px] px-2.5 py-1.5 text-[11px] resize-none"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-foreground mb-1">Prioridad</label>
                    <select
                      value={taskForm.priority}
                      onChange={(e) => setTaskForm((prev) => ({ ...prev, priority: e.target.value }))}
                      className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px]"
                    >
                      <option value="">Sin prioridad</option>
                      {priorities.map((p) => (
                        <option key={p.id_priority} value={p.id_priority}>{p.name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-foreground mb-1">Fecha limite</label>
                    <DatePickerField
                      value={taskForm.dueDate}
                      onChange={(value) => setTaskForm((prev) => ({ ...prev, dueDate: value }))}
                      minDate={minDueDate}
                      maxDate={maxDueDate}
                      placeholder="Selecciona una fecha"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-foreground mb-1">Asignado</label>
                    <TaskAssigneePicker
                      users={assignableUsers}
                      selectedIds={taskForm.assignedTo.map((value) => Number(value))}
                      onChange={(selectedIds) => setTaskForm((prev) => ({
                        ...prev,
                        assignedTo: selectedIds.map((id) => String(id)),
                      }))}
                      disabled={!canEditAssignment}
                      emptyText="Sin personas asignadas"
                    />
                    {!canEditAssignment && (
                      <p className="text-[10px] text-muted-foreground mt-1">Tu rol no puede reasignar tareas.</p>
                    )}
                    {canEditAssignment && (
                      <p className="text-[10px] text-muted-foreground mt-1">La primera persona seleccionada se mantiene como responsable principal para compatibilidad.</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 pt-1">                    {canDeleteTask && (
                      <button
                        type="button"
                        onClick={handleDeleteTask}
                        disabled={deletingTask}
                        className="h-7 px-3 border border-destructive/30 rounded-[3px] text-[11px] text-destructive hover:bg-destructive/10 disabled:opacity-50"
                      >
                        {deletingTask ? 'Eliminando…' : 'Eliminar'}
                      </button>
                    )}                    <button
                      type="button"
                      onClick={() => setIsEditingTask(false)}
                      className="h-7 px-3 border border-border rounded-[3px] text-[11px]"
                    >
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      disabled={savingTask}
                      className="h-7 px-3 bg-primary text-primary-foreground rounded-[3px] text-[11px] disabled:opacity-50"
                    >
                      {savingTask ? 'Guardando...' : 'Guardar cambios'}
                    </button>
                  </div>
                </form>
              ) : (
                <div>
                  <div>
                    <h2 className="text-[14px] font-semibold text-foreground leading-snug">{task.title}</h2>
                  </div>
                  {task.description && (
                    <p className="text-[12px] text-muted-foreground mt-1.5 leading-relaxed">{task.description}</p>
                  )}
                </div>
              )}

              {/* Metadata */}
              <div className="bg-surface-secondary/50 rounded-[4px] p-3 space-y-2">
                {assignedNames.length > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-[0.06em]">Asignado</span>
                    <div className="text-[11px] text-foreground flex items-center gap-1 flex-wrap justify-end max-w-[220px]">
                      <User className="w-3 h-3 shrink-0" />
                      <span className="text-right">{assignedNames.join(', ')}</span>
                    </div>
                  </div>
                )}
                {task.due_date && (
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-[0.06em]">Fecha límite</span>
                    <span className={`text-[11px] flex items-center gap-1 ${isOverdue ? 'text-destructive font-semibold' : 'text-foreground'}`}>
                      <Calendar className="w-3 h-3" />{task.due_date}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground uppercase tracking-[0.06em]">Creada</span>
                  <span className="text-[11px] text-muted-foreground">{task.created_at.slice(0, 10)}</span>
                </div>
              </div>

              {/* Task tags */}
              <div>
                <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em] mb-2">
                  Tags
                </p>
                <div className="space-y-2">
                  <input
                    type="text"
                    value={tagSearch}
                    onChange={(e) => setTagSearch(e.target.value)}
                    placeholder="Buscar tags..."
                    className="w-full h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px]"
                    disabled={!canEditTask}
                  />
                  <div className="flex flex-wrap gap-1.5">
                    {selectedTaskTags.length > 0 ? selectedTaskTags.map((tag) => (
                      <span
                        key={tag.id_tag}
                        className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-[10px]"
                      >
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tag.color || '#56697f' }} />
                        {tag.name}
                        {canEditTask && (
                          <button
                            type="button"
                            onClick={() => void handleRemoveTaskTag(tag.id_tag)}
                            disabled={savingTagId === tag.id_tag}
                            className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        )}
                      </span>
                    )) : <span className="text-[11px] text-muted-foreground">Sin tags.</span>}
                  </div>
                  {canEditTask && (
                    <div className="flex flex-wrap gap-1.5">
                      {searchableTags.length > 0 ? searchableTags.map((tag) => (
                        <button
                          key={tag.id_tag}
                          type="button"
                          onClick={() => void handleAddTaskTag(tag.id_tag)}
                          disabled={savingTagId === tag.id_tag}
                          className="inline-flex items-center gap-1 rounded-[3px] border border-border bg-card px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                        >
                          {savingTagId === tag.id_tag ? <Loader2 className="w-3 h-3 animate-spin" /> : <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tag.color || '#56697f' }} />}
                          {tag.name}
                        </button>
                      )) : <span className="text-[10px] text-muted-foreground">No hay tags para agregar.</span>}
                    </div>
                  )}
                  {canEditTask && onCreateTag && (
                    <button
                      type="button"
                      onClick={() => setShowNewTagForm(true)}
                      className="inline-flex items-center gap-1 rounded-[3px] border border-dashed border-border px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:border-border/80 transition-colors mt-0.5"
                    >
                      <Plus className="w-3 h-3" /> Nuevo tag
                    </button>
                  )}
                </div>
              </div>

              {/* Comments */}
              <div>
                  <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-[0.06em] mb-2 flex items-center gap-1.5">
                    <MessageSquare className="w-3 h-3" /> Comentarios ({comments.length})
                  </p>
                  {loadingComments ? (
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                      <Loader2 className="w-3 h-3 animate-spin" /> Cargando…
                    </div>
                  ) : comments.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground">Sin comentarios aún.</p>
                  ) : (
                    <div className="space-y-2">
                      {comments.map((c) => (
                        <div key={c.id_comment} className="p-2.5 bg-surface-secondary/50 rounded-[4px]">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-medium text-foreground">
                              {c.user ? (userMap.get(c.user) ?? `User #${c.user}`) : 'Sistema'}
                            </span>
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-muted-foreground">{formatCommentTimestamp(c.created_at)}</span>
                              {currentUserId != null && c.user === currentUserId && (
                                <>
                                  <button
                                    onClick={() => handleStartEditComment(c)}
                                    className="text-muted-foreground hover:text-foreground"
                                    title="Editar comentario"
                                  >
                                    <Pencil className="w-3 h-3" />
                                  </button>
                                  <button
                                    onClick={() => handleDeleteComment(c.id_comment)}
                                    className="text-muted-foreground hover:text-destructive"
                                    title="Eliminar comentario"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </button>
                                </>
                              )}
                            </div>
                          </div>

                          {editingCommentId === c.id_comment ? (
                            <div className="space-y-1.5">
                              <input
                                type="text"
                                value={editingCommentContent}
                                onChange={(e) => setEditingCommentContent(e.target.value)}
                                className="w-full h-7 bg-card border border-border rounded-[3px] px-2 text-[11px]"
                              />
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleUpdateComment(c.id_comment)}
                                  className="h-6 px-2 bg-primary text-primary-foreground rounded-[3px] text-[10px]"
                                >
                                  Guardar
                                </button>
                                <button
                                  onClick={() => {
                                    setEditingCommentId(null);
                                    setEditingCommentContent('');
                                  }}
                                  className="h-6 px-2 border border-border rounded-[3px] text-[10px]"
                                >
                                  Cancelar
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p className="text-[11px] text-muted-foreground leading-relaxed">{c.content}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Add comment form */}
                  <form onSubmit={handleAddComment} className="mt-2 flex gap-1.5">
                    <input
                      type="text"
                      value={newComment}
                      onChange={(e) => setNewComment(e.target.value)}
                      placeholder="Agregar comentario…"
                      className="flex-1 h-7 bg-surface-secondary border border-border rounded-[3px] px-2.5 text-[11px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
                    />
                    <button
                      type="submit"
                      disabled={sendingComment || !newComment.trim()}
                      className="h-7 px-2.5 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors disabled:opacity-50"
                    >
                      <Send className="w-3 h-3" />
                    </button>
                  </form>
                </div>
              </div>

              {/* Footer */}
              <div className="px-4 py-3 border-t border-border shrink-0">
                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <GitCommit className="w-3 h-3" /> ID: {task.id_task}
                  </span>
                  <button
                    onClick={onClose}
                    className="px-3 py-1 bg-surface-secondary hover:bg-accent text-foreground text-[11px] font-medium rounded-[3px] transition-colors"
                  >
                    Cerrar
                  </button>
                </div>
              </div>
              </div>

              {showWarningsSidePanel && (
                <div className="flex-1 min-w-0 border-l border-border bg-surface-secondary/20 flex flex-col">
                  <div className="px-4 py-3 border-b border-border bg-warning/5 shrink-0">
                    <p className="text-[11px] font-medium text-foreground flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-warning" /> Warnings y Conexiones
                    </p>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {loadingWarnings ? (
                      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                        <Loader2 className="w-3 h-3 animate-spin" /> Cargando warnings…
                      </div>
                    ) : activeWarnings.length > 0 ? (
                      <div className="space-y-2">
                        {activeWarnings.map((w) => (
                          <div key={w.id_warning} className="p-2.5 bg-warning/5 border border-warning/20 rounded-[4px]">
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-[11px] text-foreground leading-relaxed">{w.message}</p>
                              <button
                                type="button"
                                onClick={() => void handleDeleteWarning(w.id_warning)}
                                disabled={!canEditTask || deletingWarningId === w.id_warning}
                                className="inline-flex items-center gap-1 rounded-[3px] border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[10px] text-destructive hover:bg-destructive/20 disabled:opacity-50"
                              >
                                {deletingWarningId === w.id_warning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                                Eliminar
                              </button>
                            </div>
                            <p className="text-[10px] text-muted-foreground mt-1">{w.created_at.slice(0, 10)}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[11px] text-muted-foreground">Sin warnings activos.</p>
                    )}

                    <div className="rounded-[4px] border border-dashed border-border p-3">
                      <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-muted-foreground mb-1">Conexiones de codigo</p>
                      <p className="text-[11px] text-muted-foreground">Proximamente aqui apareceran referencias de commits, diffs y archivos relacionados a esta tarea.</p>
                    </div>
                  </div>
                </div>
              )}
          </div>
        )}
      </div>

      {/* New tag modal */}
      {showNewTagForm && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <form
            onSubmit={(e) => { e.preventDefault(); void handleCreateAndAddTag(); }}
            className="w-full max-w-sm rounded-[8px] border border-border bg-card overflow-hidden shadow-lg"
          >
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[13px] font-semibold text-foreground">Nuevo tag</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">Define un nombre y un color para el tag.</p>
            </div>
            <div className="px-4 py-4 space-y-4">
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-foreground">Nombre</label>
                <input
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                  placeholder="ej. Bug, Feature, Urgente…"
                  className="w-full h-9 rounded-[4px] border border-border bg-surface-secondary px-3 text-[12px] placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/50"
                  autoFocus
                />
              </div>
              <div className="border-t border-border/60" />
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-foreground">Color</label>
                <TagColorPicker value={newTagColor} onChange={setNewTagColor} />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-border bg-surface-secondary/30">
              <button
                type="button"
                onClick={() => { setShowNewTagForm(false); setNewTagName(''); setNewTagColor('#56697f'); }}
                className="h-8 px-3 border border-border rounded-[4px] text-[11px] hover:bg-accent transition-colors"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={!newTagName.trim() || creatingTag}
                className="h-8 px-3 bg-primary text-primary-foreground rounded-[4px] text-[11px] disabled:opacity-40 transition-opacity inline-flex items-center gap-1"
              >
                {creatingTag ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                Crear tag
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
