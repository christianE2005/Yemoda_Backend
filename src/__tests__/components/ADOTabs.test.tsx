import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ADOTabs } from '../../app/components/ADOTabs';

const baseTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'tasks', label: 'Tasks', count: 12 },
  { id: 'team', label: 'Team', count: 0 },
];

describe('ADOTabs', () => {
  it('renders all tab labels', () => {
    render(<ADOTabs tabs={baseTabs} activeTab="overview" onTabChange={() => {}} />);
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
    expect(screen.getByText('Team')).toBeInTheDocument();
  });

  it('renders count badges when provided', () => {
    render(<ADOTabs tabs={baseTabs} activeTab="overview" onTabChange={() => {}} />);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('does not render count badge when count is undefined', () => {
    render(<ADOTabs tabs={[{ id: 'a', label: 'No Count' }]} activeTab="a" onTabChange={() => {}} />);
    const tab = screen.getByRole('tab');
    // Active tab has label span + underline span, but no count badge
    const spans = tab.querySelectorAll('span');
    expect(spans.length).toBe(2); // label + underline (no count)
  });

  it('marks active tab with aria-selected=true', () => {
    render(<ADOTabs tabs={baseTabs} activeTab="tasks" onTabChange={() => {}} />);
    const tasksTab = screen.getByText('Tasks').closest('[role="tab"]');
    const overviewTab = screen.getByText('Overview').closest('[role="tab"]');
    expect(tasksTab).toHaveAttribute('aria-selected', 'true');
    expect(overviewTab).toHaveAttribute('aria-selected', 'false');
  });

  it('calls onTabChange with correct tab id on click', () => {
    const handler = vi.fn();
    render(<ADOTabs tabs={baseTabs} activeTab="overview" onTabChange={handler} />);
    fireEvent.click(screen.getByText('Team'));
    expect(handler).toHaveBeenCalledWith('team');
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('renders tablist role', () => {
    render(<ADOTabs tabs={baseTabs} activeTab="overview" onTabChange={() => {}} />);
    expect(screen.getByRole('tablist')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    const tabs = [{ id: 'x', label: 'With Icon', icon: <svg data-testid="icon" /> }];
    render(<ADOTabs tabs={tabs} activeTab="x" onTabChange={() => {}} />);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <ADOTabs tabs={baseTabs} activeTab="overview" onTabChange={() => {}} className="mt-4" />
    );
    expect(container.firstChild).toHaveClass('mt-4');
  });

  it('shows active underline only on active tab', () => {
    render(<ADOTabs tabs={baseTabs} activeTab="tasks" onTabChange={() => {}} />);
    const tasksTab = screen.getByText('Tasks').closest('[role="tab"]');
    const overviewTab = screen.getByText('Overview').closest('[role="tab"]');
    // Active tab has an extra span child for the underline
    const tasksSpans = tasksTab!.querySelectorAll(':scope > span');
    const overviewSpans = overviewTab!.querySelectorAll(':scope > span');
    // Active tab should have more spans (label + count + underline)
    expect(tasksSpans.length).toBeGreaterThan(overviewSpans.length);
  });
});
