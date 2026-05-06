import { ReactNode } from 'react';

export interface CommandBarAction {
  id?: string;
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'destructive';
  disabled?: boolean;
}

export interface CommandBarFilter {
  id?: string;
  label: string;
  value?: string;
  active: boolean;
  count?: number;
  onClick: () => void;
}

export interface CommandBarViewOption {
  id?: string;
  value: string;
  icon: ReactNode;
  label?: string;
}

interface CommandBarProps {
  actions?: CommandBarAction[];
  filters?: CommandBarFilter[];
  viewMode?: string;
  viewOptions?: CommandBarViewOption[];
  onViewChange?: (value: string) => void;
  rightSlot?: ReactNode;
  className?: string;
}

export function CommandBar({
  actions = [],
  filters = [],
  viewMode,
  viewOptions = [],
  onViewChange,
  rightSlot,
  className = '',
}: CommandBarProps) {
  const variantClass: Record<string, string> = {
    default:
      'bg-card border border-border text-foreground hover:bg-accent',
    primary:
      'bg-primary text-primary-foreground hover:bg-primary-hover border border-primary',
    destructive:
      'bg-destructive/10 text-destructive border border-destructive/30 hover:bg-destructive/20',
  };

  return (
    <div
      className={`flex items-center gap-2 px-4 py-1.5 border-b border-border bg-surface-secondary min-h-[36px] ${className}`}
    >
      {/* Primary actions (left) */}
      {actions.length > 0 && (
        <div className="flex items-center gap-1">
          {actions.map((action, i) => (
            <button
              key={action.id ?? action.label ?? i}
              onClick={action.onClick}
              disabled={action.disabled}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[3px] text-[12px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                variantClass[action.variant ?? 'default']
              }`}
            >
              {action.icon}
              {action.label}
            </button>
          ))}
        </div>
      )}

      {/* Separator between actions and filters */}
      {actions.length > 0 && filters.length > 0 && (
        <div className="h-4 w-px bg-border" />
      )}

      {/* Filters as pills */}
      {filters.length > 0 && (
        <div className="flex items-center gap-1">
          {filters.map((filter, i) => (
            <button
              key={filter.id ?? filter.value ?? filter.label ?? i}
              onClick={filter.onClick}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors ${
                filter.active
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card border border-border text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              {filter.label}
              {filter.count !== undefined && (
                <span
                  className={`ml-0.5 px-1 rounded-full text-[10px] font-bold leading-tight ${
                    filter.active
                      ? 'bg-white/20 text-white'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {filter.count}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right slot (search, custom content) */}
      {rightSlot && <div className="flex items-center gap-2">{rightSlot}</div>}

      {/* View Toggle */}
      {viewOptions.length > 0 && onViewChange && (
        <div className="flex items-center border border-border rounded-[3px] overflow-hidden">
          {viewOptions.map((opt, i) => (
            <button
              key={opt.id ?? opt.value ?? i}
              onClick={() => onViewChange(opt.value)}
              title={opt.label}
              className={`p-1.5 transition-colors ${
                viewMode === opt.value
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              {opt.icon}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
