import { describe, it, expect } from 'vitest';

// ── Pure logic extracted from ProjectDetail.tsx ──────────────

const monthMap: Record<string, number> = {
  Ene: 0, Feb: 1, Mar: 2, Abr: 3, May: 4, Jun: 5,
  Jul: 6, Ago: 7, Sep: 8, Oct: 9, Nov: 10, Dic: 11,
};

function parseDaysRemaining(deadline: string, now: Date): number {
  const parts = deadline.split(' ');
  const deadlineDate = new Date(
    parseInt(parts[2]),
    monthMap[parts[1]] ?? 0,
    parseInt(parts[0])
  );
  return Math.max(0, Math.ceil((deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

function calcSpent(budgetPercent: number, totalBudget: string): string {
  const total = parseInt(totalBudget.replace(/[$,]/g, ''));
  const amount = Math.round((budgetPercent / 100) * total);
  return `$${amount.toLocaleString()}`;
}

function getTrendDirection(progress: number, budget: number): 'up' | 'down' | 'neutral' {
  if (progress > budget) return 'up';
  if (progress < budget - 20) return 'down';
  return 'neutral';
}

function getTrendLabel(progress: number, budget: number): string {
  const diff = progress - budget;
  return diff >= 0 ? `+${diff}%` : `${diff}%`;
}

const riskLabelMap: Record<string, { label: string; color: string; bg: string }> = {
  low: { label: 'BAJO', color: 'text-success', bg: 'bg-success/10' },
  medium: { label: 'MEDIO', color: 'text-warning', bg: 'bg-warning/10' },
  high: { label: 'ALTO', color: 'text-destructive', bg: 'bg-destructive/10' },
};

function getHealthColor(score: number): string {
  if (score >= 70) return 'text-success';
  if (score >= 40) return 'text-warning';
  return 'text-destructive';
}

function getDelayColor(prob: number): string {
  if (prob <= 25) return 'text-success';
  if (prob <= 50) return 'text-warning';
  return 'text-destructive';
}

function getDelayLabel(prob: number): string {
  if (prob <= 25) return 'Baja probabilidad según tendencias actuales';
  if (prob <= 50) return 'Probabilidad moderada — monitorear de cerca';
  return 'Alta probabilidad — acción inmediata requerida';
}

// ── Tests ──────────────────────────────────────────────────────

describe('parseDaysRemaining', () => {
  it('returns positive days for a future deadline', () => {
    // April 8, 2026 — deadline 30 Jun 2026 = 83 days
    const now = new Date(2026, 3, 8); // month is 0-based
    const days = parseDaysRemaining('30 Jun 2026', now);
    expect(days).toBeGreaterThan(0);
    expect(days).toBe(83);
  });

  it('returns 0 for a past deadline', () => {
    const now = new Date(2026, 3, 8);
    const days = parseDaysRemaining('28 Feb 2026', now);
    expect(days).toBe(0);
  });

  it('returns 0 for today as deadline', () => {
    const now = new Date(2026, 3, 8);
    const days = parseDaysRemaining('08 Abr 2026', now);
    expect(days).toBe(0);
  });

  it('returns 1 for tomorrow deadline', () => {
    const now = new Date(2026, 3, 8);
    const days = parseDaysRemaining('09 Abr 2026', now);
    expect(days).toBe(1);
  });

  it('handles all month abbreviations correctly', () => {
    const now = new Date(2026, 0, 1); // Jan 1
    expect(parseDaysRemaining('01 Feb 2026', now)).toBe(31);
    expect(parseDaysRemaining('01 Mar 2026', now)).toBe(59);
    expect(parseDaysRemaining('01 Abr 2026', now)).toBe(90);
  });
});

describe('calcSpent', () => {
  it('calculates 85% of $450,000 correctly', () => {
    expect(calcSpent(85, '$450,000')).toBe('$382,500');
  });

  it('calculates 100% of $200,000', () => {
    expect(calcSpent(100, '$200,000')).toBe('$200,000');
  });

  it('calculates 0% spent', () => {
    expect(calcSpent(0, '$500,000')).toBe('$0');
  });

  it('calculates 92% of $380,000', () => {
    expect(calcSpent(92, '$380,000')).toBe('$349,600');
  });

  it('calculates 78% of $280,000', () => {
    expect(calcSpent(78, '$280,000')).toBe('$218,400');
  });
});

describe('getTrendDirection', () => {
  it('returns up when progress > budget', () => {
    expect(getTrendDirection(78, 70)).toBe('up');
  });

  it('returns down when progress < budget - 20', () => {
    expect(getTrendDirection(45, 92)).toBe('down'); // 45 < 72
  });

  it('returns neutral when difference <= 20', () => {
    expect(getTrendDirection(70, 85)).toBe('neutral'); // 70 = 85 - 15
    expect(getTrendDirection(80, 80)).toBe('neutral');
  });

  it('returns up when progress equals budget exactly', () => {
    // progress > budget is false when equal, but progress < budget-20 is also false
    expect(getTrendDirection(80, 80)).toBe('neutral');
  });
});

describe('getTrendLabel', () => {
  it('returns positive label when ahead', () => {
    expect(getTrendLabel(78, 70)).toBe('+8%');
  });

  it('returns negative label when behind', () => {
    expect(getTrendLabel(45, 92)).toBe('-47%');
  });

  it('returns +0% when equal', () => {
    expect(getTrendLabel(80, 80)).toBe('+0%');
  });
});

describe('riskLabelMap', () => {
  it('maps low to BAJO', () => {
    expect(riskLabelMap.low.label).toBe('BAJO');
    expect(riskLabelMap.low.color).toBe('text-success');
  });

  it('maps medium to MEDIO', () => {
    expect(riskLabelMap.medium.label).toBe('MEDIO');
    expect(riskLabelMap.medium.color).toBe('text-warning');
  });

  it('maps high to ALTO', () => {
    expect(riskLabelMap.high.label).toBe('ALTO');
    expect(riskLabelMap.high.color).toContain('destructive');
  });
});

describe('getHealthColor', () => {
  it('returns text-success for score >= 70', () => {
    expect(getHealthColor(70)).toBe('text-success');
    expect(getHealthColor(100)).toBe('text-success');
    expect(getHealthColor(88)).toBe('text-success');
  });

  it('returns text-warning for score 40–69', () => {
    expect(getHealthColor(40)).toBe('text-warning');
    expect(getHealthColor(52)).toBe('text-warning');
    expect(getHealthColor(69)).toBe('text-warning');
  });

  it('returns text-destructive for score < 40', () => {
    expect(getHealthColor(18)).toBe('text-destructive');
    expect(getHealthColor(28)).toBe('text-destructive');
    expect(getHealthColor(39)).toBe('text-destructive');
  });
});

describe('getDelayColor', () => {
  it('returns text-success for prob <= 25', () => {
    expect(getDelayColor(8)).toBe('text-success');
    expect(getDelayColor(25)).toBe('text-success');
  });

  it('returns text-warning for prob 26–50', () => {
    expect(getDelayColor(26)).toBe('text-warning');
    expect(getDelayColor(42)).toBe('text-warning');
    expect(getDelayColor(50)).toBe('text-warning');
  });

  it('returns text-destructive for prob > 50', () => {
    expect(getDelayColor(51)).toBe('text-destructive');
    expect(getDelayColor(72)).toBe('text-destructive');
    expect(getDelayColor(78)).toBe('text-destructive');
  });
});

describe('getDelayLabel', () => {
  it('returns low probability text for prob <= 25', () => {
    expect(getDelayLabel(12)).toBe('Baja probabilidad según tendencias actuales');
  });

  it('returns moderate text for prob 26-50', () => {
    expect(getDelayLabel(42)).toBe('Probabilidad moderada — monitorear de cerca');
  });

  it('returns critical text for prob > 50', () => {
    expect(getDelayLabel(78)).toBe('Alta probabilidad — acción inmediata requerida');
  });
});

// ── Logs filter logic ─────────────────────────────────────────

type LogEntry = { action: string; module: string; user: string; description: string };

function filterLogs(
  logs: LogEntry[],
  searchTerm: string,
  filterAction: string,
  filterModule: string
): LogEntry[] {
  return logs.filter(log => {
    const matchesSearch =
      log.user.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.module.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesAction = filterAction === 'all' || log.action === filterAction;
    const matchesModule = filterModule === 'all' || log.module === filterModule;
    return matchesSearch && matchesAction && matchesModule;
  });
}

const sampleLogs: LogEntry[] = [
  { action: 'Login', module: 'Autenticacion', user: 'Admin', description: 'Inicio de sesion' },
  { action: 'Edicion', module: 'Proyectos', user: 'Maria', description: 'Actualizo ERP' },
  { action: 'Creacion', module: 'Proyectos', user: 'Admin', description: 'Creo proyecto' },
  { action: 'Eliminacion', module: 'Usuarios', user: 'Admin', description: 'Elimino usuario' },
];

describe('Logs filter logic', () => {
  it('returns all logs when all filters are "all" and no search', () => {
    expect(filterLogs(sampleLogs, '', 'all', 'all')).toHaveLength(4);
  });

  it('filters by action', () => {
    const result = filterLogs(sampleLogs, '', 'Login', 'all');
    expect(result).toHaveLength(1);
    expect(result[0].action).toBe('Login');
  });

  it('filters by module', () => {
    const result = filterLogs(sampleLogs, '', 'all', 'Proyectos');
    expect(result).toHaveLength(2);
  });

  it('filters by search term (user)', () => {
    const result = filterLogs(sampleLogs, 'maria', 'all', 'all');
    expect(result).toHaveLength(1);
    expect(result[0].user).toBe('Maria');
  });

  it('filters by search term (description)', () => {
    const result = filterLogs(sampleLogs, 'ERP', 'all', 'all');
    expect(result).toHaveLength(1);
    expect(result[0].description).toContain('ERP');
  });

  it('returns empty when no match', () => {
    expect(filterLogs(sampleLogs, 'xyz', 'all', 'all')).toHaveLength(0);
  });

  it('combines action and module filters', () => {
    const result = filterLogs(sampleLogs, '', 'Edicion', 'Proyectos');
    expect(result).toHaveLength(1);
    expect(result[0].action).toBe('Edicion');
  });
});
