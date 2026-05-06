import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../../app/components/StatusBadge';

describe('StatusBadge', () => {
  describe('dot variant (default)', () => {
    it('renders default label for success', () => {
      render(<StatusBadge status="success" />);
      expect(screen.getByText('En tiempo')).toBeInTheDocument();
    });

    it('renders default label for on_track', () => {
      render(<StatusBadge status="on_track" />);
      expect(screen.getByText('En tiempo')).toBeInTheDocument();
    });

    it('renders default label for warning/at_risk', () => {
      render(<StatusBadge status="at_risk" />);
      expect(screen.getByText('En riesgo')).toBeInTheDocument();
    });

    it('renders default label for danger/delayed', () => {
      render(<StatusBadge status="delayed" />);
      expect(screen.getByText('Retrasado')).toBeInTheDocument();
    });

    it('renders default label for info', () => {
      render(<StatusBadge status="info" />);
      expect(screen.getByText('Info')).toBeInTheDocument();
    });

    it('renders default label for neutral', () => {
      render(<StatusBadge status="neutral" />);
      expect(screen.getByText('Neutral')).toBeInTheDocument();
    });

    it('uses custom text when provided', () => {
      render(<StatusBadge status="success" text="Completado" />);
      expect(screen.getByText('Completado')).toBeInTheDocument();
    });

    it('renders colored dot element', () => {
      const { container } = render(<StatusBadge status="success" />);
      const dot = container.querySelector('.rounded-full.shrink-0');
      expect(dot).toBeInTheDocument();
    });
  });

  describe('pill variant', () => {
    it('renders as pill with border', () => {
      const { container } = render(<StatusBadge status="warning" variant="pill" />);
      const pill = container.firstChild as HTMLElement;
      expect(pill.className).toContain('rounded-full');
      expect(pill.className).toContain('border');
      expect(screen.getByText('En riesgo')).toBeInTheDocument();
    });

    it('applies sm size classes', () => {
      const { container } = render(<StatusBadge status="danger" variant="pill" size="sm" />);
      const pill = container.firstChild as HTMLElement;
      expect(pill.className).toContain('text-[11px]');
    });
  });

  describe('icon-only variant', () => {
    it('renders just a colored dot with title', () => {
      const { container } = render(<StatusBadge status="danger" variant="icon-only" />);
      const dot = container.firstChild as HTMLElement;
      expect(dot.tagName.toLowerCase()).toBe('span');
      expect(dot).toHaveAttribute('title', 'Retrasado');
      expect(dot.className).toContain('rounded-full');
    });

    it('does not render text label', () => {
      render(<StatusBadge status="success" variant="icon-only" />);
      expect(screen.queryByText('En tiempo')).not.toBeInTheDocument();
    });
  });

  describe('size prop', () => {
    it('defaults to md', () => {
      const { container } = render(<StatusBadge status="success" />);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('text-xs');
    });

    it('uses sm sizing', () => {
      const { container } = render(<StatusBadge status="success" size="sm" />);
      const badge = container.firstChild as HTMLElement;
      expect(badge.className).toContain('text-[11px]');
    });
  });
});
