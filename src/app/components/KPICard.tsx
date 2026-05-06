import { ReactNode } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  icon?: ReactNode;
  status?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  accentColor?: 'primary' | 'success' | 'warning' | 'destructive' | 'info' | 'ai';
  sparkline?: number[];
}

const accentMap: Record<string, string> = {
  primary: 'border-l-primary',
  success: 'border-l-success',
  warning: 'border-l-warning',
  destructive: 'border-l-destructive',
  info: 'border-l-info',
  ai: 'border-l-[var(--ai)]',
};

export function KPICard({
  title,
  value,
  subtitle,
  trend,
  trendValue,
  icon,
  accentColor,
  sparkline,
}: KPICardProps) {
  const getTrendIcon = () => {
    if (trend === 'up') return <TrendingUp className="w-3 h-3" />;
    if (trend === 'down') return <TrendingDown className="w-3 h-3" />;
    return <Minus className="w-3 h-3" />;
  };

  const getTrendColor = () => {
    if (trend === 'up') return 'text-success';
    if (trend === 'down') return 'text-destructive';
    return 'text-muted-foreground';
  };

  const borderClass = accentColor ? `border-l-[3px] ${accentMap[accentColor] ?? ''}` : '';

  return (
    <div className={`bg-card border border-border rounded-[4px] px-3.5 py-2.5 transition-colors duration-100 hover:border-foreground/15 group ${borderClass}`}>
      <div className="flex items-center gap-3">
        {icon && (
          <div className="text-muted-foreground/50 group-hover:text-muted-foreground transition-colors shrink-0">
            {icon}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-muted-foreground truncate">
            {title}
          </p>
          <div className="flex items-baseline gap-2 mt-0.5">
            <span className="text-[20px] font-semibold text-foreground tracking-tight leading-none">
              {value}
            </span>
            {trendValue && (
              <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium ${getTrendColor()}`}>
                {getTrendIcon()}
                {trendValue}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{subtitle}</p>
          )}
        </div>
        {sparkline && sparkline.length > 1 && (
          <MiniSparkline data={sparkline} />
        )}
      </div>
    </div>
  );
}

function MiniSparkline({ data }: { data: number[] }) {
  const w = 48;
  const h = 16;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={w} height={h} className="shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-primary/40"
      />
    </svg>
  );
}
