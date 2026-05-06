import { useMemo, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { Calendar } from './ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';

interface DatePickerFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  minDate?: string;
  maxDate?: string;
}

function parseDateValue(value: string) {
  if (!value) return undefined;
  const parsed = parseISO(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

export function DatePickerField({
  value,
  onChange,
  placeholder = 'Selecciona una fecha',
  disabled = false,
  minDate,
  maxDate,
}: DatePickerFieldProps) {
  const [open, setOpen] = useState(false);

  const selectedDate = useMemo(() => parseDateValue(value), [value]);
  const minDateValue = useMemo(() => parseDateValue(minDate ?? ''), [minDate]);
  const maxDateValue = useMemo(() => parseDateValue(maxDate ?? ''), [maxDate]);
  const buttonLabel = selectedDate
    ? format(selectedDate, "dd 'de' MMM yyyy", { locale: es })
    : placeholder;

  const isDateDisabled = (date: Date) => {
    if (minDateValue && date < minDateValue) return true;
    if (maxDateValue && date > maxDateValue) return true;
    return false;
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className="inline-flex h-9 w-full items-center justify-between rounded-[4px] border border-border bg-surface-secondary px-3 text-left text-[12px] font-normal text-foreground transition-colors hover:bg-accent/60 disabled:opacity-50"
        >
          <span className={selectedDate ? 'text-foreground' : 'text-muted-foreground'}>{buttonLabel}</span>
          <CalendarDays className="w-4 h-4 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto rounded-[6px] border-border bg-card p-0 shadow-xl">
        <Calendar
          mode="single"
          selected={selectedDate}
          disabled={isDateDisabled}
          onSelect={(date) => {
            if (!date) return;
            if (isDateDisabled(date)) return;
            onChange(format(date, 'yyyy-MM-dd'));
            setOpen(false);
          }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}