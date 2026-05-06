interface StatusBadgeProps {
  status: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'on_track' | 'at_risk' | 'delayed' | 'active' | 'completed' | 'on_hold' | 'cancelled' | 'planning' | 'review' | 'retired';
  text?: string;
  size?: 'sm' | 'md';
  variant?: 'dot' | 'pill' | 'icon-only';
}

export function StatusBadge({ status, text, size = 'md', variant = 'dot' }: StatusBadgeProps) {
  const getStatusConfig = () => {
    switch (status) {
      case 'success':
      case 'on_track':
        return { dot: 'bg-success', pill: 'bg-success/10 text-success border-success/20', label: text || 'En tiempo' };
      case 'active':
        return { dot: 'bg-success', pill: 'bg-success/10 text-success border-success/20', label: text || 'Activo' };
      case 'planning':
        return { dot: 'bg-slate-500', pill: 'bg-slate-500/10 text-slate-700 border-slate-500/20 dark:text-slate-200', label: text || 'Planeación' };
      case 'warning':
      case 'at_risk':
        return { dot: 'bg-warning', pill: 'bg-warning/10 text-warning border-warning/20', label: text || 'En riesgo' };
      case 'on_hold':
        return { dot: 'bg-warning', pill: 'bg-warning/10 text-warning border-warning/20', label: text || 'En pausa' };
      case 'review':
        return { dot: 'bg-violet-500', pill: 'bg-violet-500/10 text-violet-700 border-violet-500/20 dark:text-violet-200', label: text || 'Revisión' };
      case 'danger':
      case 'delayed':
        return { dot: 'bg-destructive', pill: 'bg-destructive/10 text-destructive border-destructive/20', label: text || 'Retrasado' };
      case 'completed':
        return { dot: 'bg-success', pill: 'bg-success/10 text-success border-success/20', label: text || 'Completado' };
      case 'info':
        return { dot: 'bg-info', pill: 'bg-info/10 text-info border-info/20', label: text || 'Info' };
      case 'retired':
        return { dot: 'bg-orange-500', pill: 'bg-orange-500/10 text-orange-700 border-orange-500/20 dark:text-orange-200', label: text || 'Retirado' };
      case 'cancelled':
        return { dot: 'bg-rose-500', pill: 'bg-rose-500/10 text-rose-700 border-rose-500/20 dark:text-rose-200', label: text || 'Cancelado' };
      default:
        return { dot: 'bg-muted-foreground', pill: 'bg-muted text-muted-foreground border-border', label: text || 'Neutral' };
    }
  };

  const config = getStatusConfig();
  const sizeClasses = size === 'sm' ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-0.5 text-xs';

  if (variant === 'pill') {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full border ${sizeClasses} font-medium ${config.pill}`}>
        {config.label}
      </span>
    );
  }

  if (variant === 'icon-only') {
    return <span className={`w-2 h-2 rounded-full shrink-0 ${config.dot}`} title={config.label} />;
  }

  return (
    <span className={`inline-flex items-center gap-1.5 rounded border border-border bg-transparent text-muted-foreground ${sizeClasses} font-medium`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${config.dot}`} />
      {config.label}
    </span>
  );
}