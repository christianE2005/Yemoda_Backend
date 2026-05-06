import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/app/components/ui/dialog';
import { Search, User, Loader2 } from 'lucide-react';

export interface AssignCandidate {
  id: number;
  name: string;
  email: string;
  avatar?: string;
  role?: string;
}

interface AssignResponsibleModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  candidates: AssignCandidate[];
  currentResponsibleId?: number;
  onAssign: (userId: number) => void;
  loading?: boolean;
  title?: string;
}

export function AssignResponsibleModal({
  open,
  onOpenChange,
  candidates,
  currentResponsibleId,
  onAssign,
  loading = false,
  title = 'Asignar Responsable',
}: AssignResponsibleModalProps) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return candidates;
    const q = query.toLowerCase();
    return candidates.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q) ||
        (c.role && c.role.toLowerCase().includes(q)),
    );
  }, [candidates, query]);

  // Reset state on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.children[activeIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && filtered[activeIndex]) {
        e.preventDefault();
        onAssign(filtered[activeIndex].id);
      }
    },
    [filtered, activeIndex, onAssign],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px] p-0 gap-0 rounded-[4px] overflow-hidden">
        <DialogHeader className="px-4 pt-4 pb-2">
          <DialogTitle className="text-sm font-semibold">{title}</DialogTitle>
        </DialogHeader>

        {/* Search input */}
        <div className="px-4 pb-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActiveIndex(0);
              }}
              onKeyDown={handleKeyDown}
              placeholder="Buscar por nombre, email o rol…"
              className="w-full h-8 pl-8 pr-3 text-[13px] bg-surface-secondary border border-border rounded-[3px] outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-colors placeholder:text-muted-foreground/60"
            />
          </div>
        </div>

        {/* Candidate list */}
        <div ref={listRef} className="max-h-[280px] overflow-y-auto px-1 pb-2">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              <span className="text-[12px]">Cargando…</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-muted-foreground">
              <User className="w-5 h-5 mb-1 opacity-40" />
              <span className="text-[12px]">Sin resultados</span>
            </div>
          ) : (
            filtered.map((c, i) => {
              const isCurrent = c.id === currentResponsibleId;
              const isActive = i === activeIndex;
              return (
                <button
                  key={c.id}
                  onClick={() => onAssign(c.id)}
                  onMouseEnter={() => setActiveIndex(i)}
                  className={`w-full flex items-center gap-3 px-3 py-2 text-left rounded-[3px] transition-colors ${
                    isActive
                      ? 'bg-accent/60'
                      : 'hover:bg-accent/40'
                  } ${isCurrent ? 'ring-1 ring-primary/30' : ''}`}
                >
                  {/* Avatar */}
                  <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0 overflow-hidden">
                    {c.avatar ? (
                      <img src={c.avatar} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-[11px] font-medium text-muted-foreground">
                        {c.name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[13px] font-medium text-foreground truncate">
                        {c.name}
                      </span>
                      {isCurrent && (
                        <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded-full font-medium shrink-0">
                          Actual
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span className="truncate">{c.email}</span>
                      {c.role && (
                        <>
                          <span className="text-border">·</span>
                          <span className="truncate">{c.role}</span>
                        </>
                      )}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
