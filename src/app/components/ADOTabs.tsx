import type { ReactNode } from 'react';

export interface ADOTab {
  id: string;
  label: string;
  count?: number;
  icon?: ReactNode;
}

interface ADOTabsProps {
  tabs: ADOTab[];
  activeTab: string;
  onTabChange: (id: string) => void;
  className?: string;
}

export function ADOTabs({ tabs, activeTab, onTabChange, className = '' }: ADOTabsProps) {
  return (
    <div className={`flex items-end gap-0 overflow-x-auto border-b border-border ${className}`} role="tablist" aria-label="Project navigation tabs">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onTabChange(tab.id)}
            className={`
              relative inline-flex shrink-0 items-center gap-1.5 px-3 py-2 text-[12px] font-medium transition-colors
              ${isActive
                ? 'text-primary'
                : 'text-muted-foreground hover:text-foreground'
              }
            `}
          >
            {tab.icon && <span className="w-3.5 h-3.5 shrink-0">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.count != null && (
              <span className={`
                inline-flex items-center justify-center min-w-[18px] h-[16px] rounded-full px-1 text-[10px] font-semibold
                ${isActive ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'}
              `}>
                {tab.count}
              </span>
            )}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary rounded-t-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
