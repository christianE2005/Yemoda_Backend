import { useMemo, useState } from 'react';
import { Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';
import {
  useApiProjects,
  useApiTags,
  useApiTasks,
} from '../hooks/useProjectData';
import { tasksService } from '../../services';
import { TagColorPicker } from '../components/TagColorPicker';

export default function Backlog() {
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  const [newTagName, setNewTagName] = useState('');
  const [newTag, setNewTag] = useState({ color: '#56697f' });

  const { data: projects, loading: loadingProjects } = useApiProjects();
  const { data: tasks, loading: loadingTasks, priorities } = useApiTasks(undefined, selectedProjectId ?? undefined);
  const { data: tags, loading: loadingTags, refetch: refetchTags } = useApiTags(selectedProjectId ?? undefined);

  const loading = loadingProjects || loadingTasks || loadingTags;

  const backlogTasks = useMemo(() => (tasks ?? []).filter((task) => task.sprint == null), [tasks]);
  const filteredTasks = useMemo(() => {
    if (selectedTagIds.length === 0) return backlogTasks;
    return backlogTasks.filter((task) => selectedTagIds.every((tagId) => task.tags.includes(tagId)));
  }, [backlogTasks, selectedTagIds]);

  const priorityById = useMemo(() => {
    const map = new Map<number, string>();
    priorities.forEach((priority) => map.set(priority.id_priority, priority.name));
    return map;
  }, [priorities]);

  const tagById = useMemo(() => {
    const map = new Map<number, { name: string; color: string }>();
    (tags ?? []).forEach((tag) => {
      map.set(tag.id_tag, { name: tag.name, color: tag.color || '#56697f' });
    });
    return map;
  }, [tags]);

  const createTag = async () => {
    if (!selectedProjectId || !newTagName.trim()) {
      toast.error('Selecciona un proyecto y escribe el nombre del tag.');
      return;
    }

    try {
      await tasksService.createTag({ project: selectedProjectId, name: newTagName.trim(), color: newTag.color });
      setNewTagName('');
      setNewTag({ color: '#56697f' });
      refetchTags();
      toast.success('Tag creado.');
    } catch {
      toast.error('No se pudo crear el tag.');
    }
  };

  return (
    <div className="px-4 pb-6 pt-3 max-w-[1600px] min-h-full flex flex-col gap-3">

      {/* ── Top shell ─────────────────────────────────────────────────────── */}
      <section className="rounded-[6px] border border-border bg-card overflow-hidden">
        {/* Header row */}
        <div className="flex items-center justify-between gap-4 px-4 py-3 border-b border-border">
          <div>
            <h1 className="text-[14px] font-semibold text-foreground">Product Backlog</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">Tareas sin sprint asignado.</p>
          </div>

          {/* Right: project selector + new tag form */}
          <div className="flex items-center gap-2 shrink-0">
            <select
              value={selectedProjectId ?? ''}
              onChange={(e) => {
                setSelectedProjectId(e.target.value ? Number(e.target.value) : null);
                setSelectedTagIds([]);
              }}
              className="h-8 min-w-[180px] rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px] text-foreground"
            >
              <option value="">Todos los proyectos</option>
              {(projects ?? []).map((project) => (
                <option key={project.id_project} value={project.id_project}>{project.name}</option>
              ))}
            </select>

            <div className="h-4 w-px bg-border" />

            <input
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void createTag(); }}
              placeholder="Nuevo tag…"
              className="h-8 w-32 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px] placeholder:text-muted-foreground/60 disabled:opacity-50"
              disabled={!selectedProjectId}
            />
            <div className={!selectedProjectId ? 'pointer-events-none opacity-50' : ''}>
              <TagColorPicker value={newTag.color} onChange={(color) => setNewTag({ color })} />
            </div>
            <button
              type="button"
              onClick={() => void createTag()}
              disabled={!selectedProjectId || !newTagName.trim()}
              className="h-8 px-2.5 rounded-[3px] border border-border bg-surface-secondary text-[11px] disabled:opacity-40 inline-flex items-center gap-1 hover:bg-accent transition-colors"
            >
              <Plus className="w-3 h-3" /> Crear tag
            </button>
          </div>
        </div>

        {/* Tag filter chips */}
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-2.5 bg-surface-secondary/30 min-h-[40px]">
          {(tags ?? []).length === 0 ? (
            <span className="text-[10px] text-muted-foreground italic">Sin tags — selecciona un proyecto para ver sus tags.</span>
          ) : (
            (tags ?? []).map((tag) => {
              const selected = selectedTagIds.includes(tag.id_tag);
              return (
                <button
                  key={tag.id_tag}
                  type="button"
                  onClick={() => setSelectedTagIds((current) => selected ? current.filter((id) => id !== tag.id_tag) : [...current, tag.id_tag])}
                  className={selected
                    ? 'inline-flex items-center h-6 px-2.5 rounded-full border text-[10px] font-medium transition-colors'
                    : 'inline-flex items-center h-6 px-2.5 rounded-full border border-border text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors'}
                  style={selected ? {
                    borderColor: `${tag.color ?? '#56697f'}88`,
                    backgroundColor: `${tag.color ?? '#56697f'}22`,
                    color: tag.color ?? '#56697f',
                  } : undefined}
                >
                  {tag.name}
                </button>
              );
            })
          )}
        </div>
      </section>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="py-16 flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : filteredTasks.length === 0 ? (
        <div className="rounded-[6px] border border-border bg-card py-16 text-center">
          <p className="text-[12px] text-muted-foreground">No hay tareas en el backlog{selectedTagIds.length > 0 ? ' con esos tags' : ''}.</p>
        </div>
      ) : (
        <div className="rounded-[6px] border border-border bg-card overflow-auto">
          <table className="w-full min-w-[880px] text-[11px]">
            <thead>
              <tr className="border-b border-border bg-surface-secondary/50">
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Título</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground w-28">Prioridad</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Tags</th>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground w-40">Proyecto</th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.map((task, i) => (
                <tr key={task.id_task} className={`border-b border-border/60 align-top hover:bg-accent/30 transition-colors ${i === filteredTasks.length - 1 ? 'border-b-0' : ''}`}>
                  <td className="px-4 py-3 min-w-[360px]">
                    <p className="text-[12px] font-medium text-foreground">{task.title}</p>
                    {task.description && <p className="mt-0.5 text-[10px] text-muted-foreground leading-relaxed line-clamp-2">{task.description}</p>}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-[11px] text-foreground">
                      {priorityById.get(task.priority) ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {task.tags.length === 0 ? (
                      <span className="text-[10px] text-muted-foreground/50">—</span>
                    ) : (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {task.tags.slice(0, 3).map((tagId) => {
                          const tag = tagById.get(tagId);
                          return (
                            <span
                              key={`${task.id_task}-${tagId}`}
                              className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
                              style={{
                                borderColor: `${tag?.color ?? '#56697f'}55`,
                                backgroundColor: `${tag?.color ?? '#56697f'}1a`,
                                color: tag?.color ?? '#56697f',
                              }}
                            >
                              {tag?.name ?? `#${tagId}`}
                            </span>
                          );
                        })}
                        {task.tags.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">+{task.tags.length - 3}</span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[11px] text-muted-foreground">
                    {(projects ?? []).find((p) => p.id_project === task.project)?.name ?? `#${task.project}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
