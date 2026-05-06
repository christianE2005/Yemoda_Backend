interface ProgressBarProps {
  value: number;
  color?: string;
  className?: string;
  height?: number;
}

export function ProgressBar({ value, color, className = '', height = 4 }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const barColor = color
    ?? (clamped >= 75 ? 'var(--success)' : clamped >= 40 ? 'var(--warning)' : 'var(--destructive)');

  return (
    <div
      className={`w-full rounded-full bg-muted/50 overflow-hidden ${className}`}
      style={{ height }}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${clamped}%`, backgroundColor: barColor }}
      />
    </div>
  );
}
