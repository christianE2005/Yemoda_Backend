import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProgressBar } from '../../app/components/ProgressBar';

describe('ProgressBar', () => {
  it('renders with progressbar role', () => {
    render(<ProgressBar value={50} />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('sets aria-valuenow to clamped value', () => {
    render(<ProgressBar value={75} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '75');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });

  it('clamps value below 0 to 0', () => {
    render(<ProgressBar value={-10} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });

  it('clamps value above 100 to 100', () => {
    render(<ProgressBar value={150} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });

  it('uses success color for value >= 75', () => {
    const { container } = render(<ProgressBar value={80} />);
    const inner = container.querySelector('[role="progressbar"] > div') as HTMLElement;
    expect(inner.style.backgroundColor).toBe('var(--success)');
  });

  it('uses warning color for value between 40 and 74', () => {
    const { container } = render(<ProgressBar value={50} />);
    const inner = container.querySelector('[role="progressbar"] > div') as HTMLElement;
    expect(inner.style.backgroundColor).toBe('var(--warning)');
  });

  it('uses destructive color for value < 40', () => {
    const { container } = render(<ProgressBar value={20} />);
    const inner = container.querySelector('[role="progressbar"] > div') as HTMLElement;
    expect(inner.style.backgroundColor).toBe('var(--destructive)');
  });

  it('uses custom color when provided', () => {
    const { container } = render(<ProgressBar value={90} color="#ff0000" />);
    const inner = container.querySelector('[role="progressbar"] > div') as HTMLElement;
    expect(inner.style.backgroundColor).toBe('rgb(255, 0, 0)');
  });

  it('sets width based on value', () => {
    const { container } = render(<ProgressBar value={63} />);
    const inner = container.querySelector('[role="progressbar"] > div') as HTMLElement;
    expect(inner.style.width).toBe('63%');
  });

  it('respects custom height', () => {
    render(<ProgressBar value={50} height={8} />);
    const bar = screen.getByRole('progressbar') as HTMLElement;
    expect(bar.style.height).toBe('8px');
  });

  it('defaults to 4px height', () => {
    render(<ProgressBar value={50} />);
    const bar = screen.getByRole('progressbar') as HTMLElement;
    expect(bar.style.height).toBe('4px');
  });

  it('applies custom className', () => {
    render(<ProgressBar value={50} className="mt-2" />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveClass('mt-2');
  });
});
