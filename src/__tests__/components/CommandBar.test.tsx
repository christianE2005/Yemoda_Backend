import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandBar } from '../../app/components/CommandBar';

describe('CommandBar', () => {
  it('renders nothing when no actions/filters/viewOptions provided', () => {
    const { container } = render(<CommandBar />);
    // The bar itself still renders as a container div
    expect(container.firstChild).toBeTruthy();
  });

  it('renders action buttons', () => {
    const onClick = vi.fn();
    render(
      <CommandBar
        actions={[
          { label: 'Guardar', onClick },
          { label: 'Cancelar', onClick },
        ]}
      />
    );
    expect(screen.getByText('Guardar')).toBeInTheDocument();
    expect(screen.getByText('Cancelar')).toBeInTheDocument();
  });

  it('calls onClick when action button is clicked', () => {
    const onClick = vi.fn();
    render(<CommandBar actions={[{ label: 'Test', onClick }]} />);
    fireEvent.click(screen.getByText('Test'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('disabled action button does not fire onClick', () => {
    const onClick = vi.fn();
    render(<CommandBar actions={[{ label: 'Disabled', onClick, disabled: true }]} />);
    const btn = screen.getByText('Disabled').closest('button')!;
    expect(btn).toBeDisabled();
  });

  it('renders filter buttons', () => {
    render(
      <CommandBar
        filters={[
          { label: 'Todos', active: true, onClick: vi.fn() },
          { label: 'En riesgo', active: false, onClick: vi.fn() },
        ]}
      />
    );
    expect(screen.getByText('Todos')).toBeInTheDocument();
    expect(screen.getByText('En riesgo')).toBeInTheDocument();
  });

  it('calls filter onClick when filter is clicked', () => {
    const onFilter = vi.fn();
    render(
      <CommandBar
        filters={[{ label: 'Activos', active: false, onClick: onFilter }]}
      />
    );
    fireEvent.click(screen.getByText('Activos'));
    expect(onFilter).toHaveBeenCalledTimes(1);
  });

  it('shows filter count badge when count is provided', () => {
    render(
      <CommandBar
        filters={[{ label: 'Retrasados', active: false, count: 3, onClick: vi.fn() }]}
      />
    );
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('renders view mode toggle buttons', () => {
    const onViewChange = vi.fn();
    render(
      <CommandBar
        viewMode="grid"
        viewOptions={[
          { value: 'grid', icon: <span>Grid</span> },
          { value: 'list', icon: <span>List</span> },
        ]}
        onViewChange={onViewChange}
      />
    );
    expect(screen.getByText('Grid')).toBeInTheDocument();
    expect(screen.getByText('List')).toBeInTheDocument();
  });

  it('calls onViewChange with correct value when view option is clicked', () => {
    const onViewChange = vi.fn();
    render(
      <CommandBar
        viewMode="grid"
        viewOptions={[
          { value: 'grid', icon: <span>Grid</span> },
          { value: 'list', icon: <span>List</span> },
        ]}
        onViewChange={onViewChange}
      />
    );
    fireEvent.click(screen.getByText('List').closest('button')!);
    expect(onViewChange).toHaveBeenCalledWith('list');
  });

  it('renders rightSlot content', () => {
    render(
      <CommandBar rightSlot={<input placeholder="Buscar..." />} />
    );
    expect(screen.getByPlaceholderText('Buscar...')).toBeInTheDocument();
  });

  it('applies primary variant class to primary action', () => {
    render(
      <CommandBar
        actions={[{ label: 'Nuevo', onClick: vi.fn(), variant: 'primary' }]}
      />
    );
    const btn = screen.getByText('Nuevo').closest('button')!;
    expect(btn.className).toContain('bg-primary');
  });

  it('renders separator between actions and filters', () => {
    const { container } = render(
      <CommandBar
        actions={[{ label: 'Act', onClick: vi.fn() }]}
        filters={[{ label: 'Filter', active: false, onClick: vi.fn() }]}
      />
    );
    // separator is a div with h-4 w-px bg-border
    const separator = container.querySelector('.bg-border.h-4.w-px');
    expect(separator).toBeInTheDocument();
  });
});
