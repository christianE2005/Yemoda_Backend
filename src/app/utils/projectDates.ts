import { isTerminalProjectStatus } from './projectStatus';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

export function formatProjectDate(date: string | null | undefined) {
  if (!date) return '—';
  const parsed = parseISO(date);
  if (Number.isNaN(parsed.getTime())) return date;
  return format(parsed, 'dd MMM yyyy', { locale: es });
}

export function getProjectDaysRemaining(endDate: string | null) {
  if (!endDate) return null;
  return Math.ceil((new Date(endDate).getTime() - Date.now()) / 86_400_000);
}

export function getProjectDaysLabel(endDate: string | null, status?: string | null) {
  if (!endDate) return { label: '—', cls: 'text-muted-foreground' };
  if (isTerminalProjectStatus(status)) {
    return { label: '—', cls: 'text-muted-foreground' };
  }

  const days = getProjectDaysRemaining(endDate);
  if (days === null) return { label: '—', cls: 'text-muted-foreground' };
  if (days < 0) return { label: 'Vencido', cls: 'text-destructive font-semibold' };
  if (days === 0) return { label: 'Hoy', cls: 'text-destructive font-semibold' };
  if (days <= 7) return { label: `${days}d`, cls: 'text-warning font-semibold' };
  return { label: `${days}d`, cls: 'text-muted-foreground' };
}

export function getProjectTimeRemainingLabel(endDate: string | null, status?: string | null) {
  if (!endDate) return { label: '—', cls: 'text-muted-foreground' };
  if (isTerminalProjectStatus(status)) return { label: '—', cls: 'text-muted-foreground' };

  const endTimestamp = new Date(endDate).getTime();
  const diffMs = endTimestamp - Date.now();
  if (Number.isNaN(endTimestamp)) return { label: '—', cls: 'text-muted-foreground' };
  if (diffMs <= 0) return { label: 'Vencido', cls: 'text-destructive font-semibold' };

  const hours = Math.ceil(diffMs / 3_600_000);
  if (hours <= 72) {
    return { label: `${hours} hora${hours === 1 ? '' : 's'}`, cls: hours <= 24 ? 'text-warning font-semibold' : 'text-muted-foreground' };
  }

  const days = Math.ceil(diffMs / 86_400_000);
  if (days < 30) {
    return { label: `${days} dia${days === 1 ? '' : 's'}`, cls: days <= 7 ? 'text-warning font-semibold' : 'text-muted-foreground' };
  }

  const months = Math.floor(days / 30);
  const remDays = days % 30;
  const monthToken = `${months} mes${months === 1 ? '' : 'es'}`;
  const dayToken = remDays > 0 ? ` ${remDays} dia${remDays === 1 ? '' : 's'}` : '';
  return { label: `${monthToken}${dayToken}`, cls: 'text-muted-foreground' };
}