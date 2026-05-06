import { AlertTriangle } from 'lucide-react';
import { Tooltip, TooltipTrigger, TooltipContent } from './ui/tooltip';

interface WarningBadgeProps {
  count: number;
  className?: string;
}

export function WarningBadge({ count, className = '' }: WarningBadgeProps) {
  if (count === 0) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-warning/15 text-warning border border-warning/20 ${className}`}
        >
          <AlertTriangle className="w-3 h-3" />
          {count}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        {count} warning{count !== 1 ? 's' : ''} activo{count !== 1 ? 's' : ''}
      </TooltipContent>
    </Tooltip>
  );
}
