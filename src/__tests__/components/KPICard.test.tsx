import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KPICard } from '../../app/components/KPICard';

describe('KPICard', () => {
  it('renders title and value', () => {
    render(<KPICard title="Avance" value="78%" />);
    expect(screen.getByText('Avance')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
  });

  it('renders numeric value', () => {
    render(<KPICard title="Proyectos" value={8} />);
    expect(screen.getByText('8')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    render(<KPICard title="Presupuesto" value="$450K" subtitle="de $500K asignados" />);
    expect(screen.getByText('de $500K asignados')).toBeInTheDocument();
  });

  it('does not render subtitle when not provided', () => {
    const { container } = render(<KPICard title="KPI" value="100" />);
    // There should be no subtitle paragraph beyond the title
    const paragraphs = container.querySelectorAll('p');
    expect(paragraphs.length).toBe(1); // only the title p
  });

  it('renders trend value when provided', () => {
    render(<KPICard title="Avance" value="78%" trend="up" trendValue="+4.3%" />);
    expect(screen.getByText('+4.3%')).toBeInTheDocument();
  });

  it('does not render trend badge when trendValue is absent', () => {
    const { container } = render(<KPICard title="KPI" value="50" trend="up" />);
    // No span with trend classes should contain icon + value
    expect(container.querySelector('[class*="bg-success"]')).toBeNull();
  });

  it('renders icon when provided', () => {
    render(<KPICard title="KPI" value="1" icon={<span data-testid="icon">📦</span>} />);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('does not render icon container when icon is absent', () => {
    const { container } = render(<KPICard title="KPI" value="1" />);
    // No w-8 h-8 icon div
    expect(container.querySelector('.w-8.h-8')).toBeNull();
  });

  it('does not apply accentColor border by default', () => {
    const { container } = render(<KPICard title="KPI" value="1" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).not.toContain('border-l-');
  });

  it('applies success accentColor border', () => {
    const { container } = render(<KPICard title="KPI" value="1" accentColor="success" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-l-success');
  });

  it('applies warning accentColor border', () => {
    const { container } = render(<KPICard title="KPI" value="1" accentColor="warning" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-l-warning');
  });

  it('applies info accentColor border', () => {
    const { container } = render(<KPICard title="KPI" value="1" accentColor="info" />);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-l-info');
  });

  it('shows TrendingUp icon for trend=up and applies success color', () => {
    const { container } = render(
      <KPICard title="KPI" value="1" trend="up" trendValue="+5%" />
    );
    const badge = container.querySelector('[class*="text-success"]');
    expect(badge).toBeInTheDocument();
  });

  it('shows TrendingDown icon for trend=down and applies destructive color', () => {
    const { container } = render(
      <KPICard title="KPI" value="1" trend="down" trendValue="-3%" />
    );
    const badge = container.querySelector('[class*="text-destructive"]');
    expect(badge).toBeInTheDocument();
  });

  it('shows neutral style for trend=neutral', () => {
    const { container } = render(
      <KPICard title="KPI" value="1" trend="neutral" trendValue="±1%" />
    );
    const badge = container.querySelector('[class*="text-muted-foreground"]');
    expect(badge).toBeInTheDocument();
  });
});
