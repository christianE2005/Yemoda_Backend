import { useMemo, useState } from 'react';
import { Search, Users, X } from 'lucide-react';

interface TaskAssigneePickerProps {
  users: Array<{ id: number; name: string }>;
  selectedIds: number[];
  onChange: (selectedIds: number[]) => void;
  disabled?: boolean;
  emptyText?: string;
}

export function TaskAssigneePicker({
  users,
  selectedIds,
  onChange,
  disabled = false,
  emptyText = 'Sin personas asignadas',
}: TaskAssigneePickerProps) {
  const [query, setQuery] = useState('');

  const filteredUsers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return users;
    return users.filter((user) => user.name.toLowerCase().includes(normalizedQuery));
  }, [users, query]);

  const selectedUsers = useMemo(
    () => selectedIds
      .map((selectedId) => users.find((user) => user.id === selectedId))
      .filter((user): user is { id: number; name: string } => Boolean(user)),
    [selectedIds, users],
  );

  const toggleUser = (userId: number) => {
    if (disabled) return;

    if (selectedIds.includes(userId)) {
      onChange(selectedIds.filter((id) => id !== userId));
      return;
    }

    onChange([...selectedIds, userId]);
  };

  const clearUser = (userId: number) => {
    if (disabled) return;
    onChange(selectedIds.filter((id) => id !== userId));
  };

  return (
    <div className={`rounded-[6px] border border-border bg-surface-secondary/35 ${disabled ? 'opacity-70' : ''}`}>
      <div className="border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
          <Users className="w-3.5 h-3.5" />
          Personas asignadas
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5 min-h-[28px]">
          {selectedUsers.length > 0 ? selectedUsers.map((user) => (
            <span
              key={user.id}
              className="inline-flex items-center gap-1 rounded-full bg-card border border-border px-2 py-1 text-[11px] text-foreground"
            >
              {user.name}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => clearUser(user.id)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Quitar a ${user.name}`}
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </span>
          )) : (
            <span className="inline-flex items-center text-[11px] text-muted-foreground">{emptyText}</span>
          )}
        </div>
      </div>

      <div className="p-3 space-y-2.5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar personas..."
            disabled={disabled}
            className="h-8 w-full rounded-[4px] border border-border bg-card pl-8 pr-3 text-[11px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed"
          />
        </div>

        <div className="max-h-[200px] overflow-y-auto space-y-1 pr-1">
          {filteredUsers.length > 0 ? filteredUsers.map((user) => {
            const checked = selectedIds.includes(user.id);
            return (
              <button
                key={user.id}
                type="button"
                onClick={() => toggleUser(user.id)}
                disabled={disabled}
                className={`flex w-full items-center gap-2 rounded-[4px] border px-2.5 py-2 text-left transition-colors ${checked
                  ? 'border-primary/40 bg-primary/10 text-foreground'
                  : 'border-transparent bg-card/70 text-muted-foreground hover:border-border hover:text-foreground'} disabled:cursor-not-allowed`}
              >
                <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] font-semibold ${checked
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-background text-transparent'}`}>
                  ✓
                </span>
                <span className="truncate text-[11px] font-medium">{user.name}</span>
              </button>
            );
          }) : (
            <div className="rounded-[4px] border border-dashed border-border bg-card/50 px-3 py-4 text-center text-[11px] text-muted-foreground">
              No hay coincidencias.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}