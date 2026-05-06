import { Link, useLocation } from 'react-router';
import {
  LayoutGrid,
  Briefcase,
  ListChecks,
  CircleUser,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
  Zap,
  BarChart3,
  Bell,
  Users,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useState } from 'react';
import { Tooltip, TooltipTrigger, TooltipContent } from './ui/tooltip';
import type { UserRole } from '../context/AuthContext';

interface NavItem {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  roles?: UserRole[];
  group?: string;
}

const navItems: NavItem[] = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutGrid, group: 'main' },
  { name: 'Backlog', path: '/backlog', icon: ListChecks, group: 'main', roles: ['admin', 'user', 'project_manager'] },
  { name: 'Proyectos', path: '/projects', icon: Briefcase, group: 'main' },
  { name: 'Reportes', path: '/reports', icon: BarChart3, group: 'analytics', roles: ['admin', 'project_manager'] },
  { name: 'Alertas', path: '/alerts', icon: Bell, group: 'analytics', roles: ['admin', 'project_manager'] },

  { name: 'Crear Usuarios', path: '/users', icon: Users, group: 'admin', roles: ['admin'] },
  { name: 'Perfil', path: '/profile', icon: CircleUser, group: 'user' },
  { name: 'Configuración', path: '/settings', icon: SlidersHorizontal, group: 'user', roles: ['admin', 'project_manager', 'user', 'stakeholder'] },
];

export function Sidebar() {
  const location = useLocation();
  const { user } = useAuth();
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem('sidebar-collapsed') === 'true';
  });
  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('sidebar-collapsed', String(next));
      return next;
    });
  };

  const filteredNavItems = navItems.filter((item) => {
    if (!item.roles) return true;
    return user && item.roles.includes(user.role);
  });

  const mainItems = filteredNavItems.filter((i) => i.group === 'main');
  const analyticsItems = filteredNavItems.filter((i) => i.group === 'analytics');
  const adminItems = filteredNavItems.filter((i) => i.group === 'admin');
  const userItems = filteredNavItems.filter((i) => i.group === 'user');

  const NavLink = ({ item }: { item: NavItem }) => {
    const Icon = item.icon;
    const isActive =
      location.pathname === item.path ||
      (item.path !== '/dashboard' && location.pathname.startsWith(item.path));

    const inner = (
      <Link
        to={item.path}
        className={`relative flex items-center gap-2.5 transition-colors duration-100 select-none
          ${collapsed ? 'justify-center px-0 py-2 mx-1 rounded-[3px]' : 'px-3 py-[6px] mx-1.5 rounded-[3px]'}
          ${
            isActive
              ? 'bg-sidebar-accent text-sidebar-accent-foreground before:absolute before:left-0 before:top-[4px] before:bottom-[4px] before:w-[2px] before:bg-primary before:rounded-r'
              : 'text-sidebar-muted hover:bg-sidebar-accent/60 hover:text-sidebar-foreground'
          }`}
      >
        <Icon
          className={`flex-shrink-0 ${isActive ? 'text-primary' : ''} ${
            collapsed ? 'w-5 h-5' : 'w-[18px] h-[18px]'
          }`}
        />
        {!collapsed && (
          <span className="text-[13px] leading-tight truncate">{item.name}</span>
        )}
      </Link>
    );

    if (collapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{inner}</TooltipTrigger>
          <TooltipContent side="right" sideOffset={8} className="text-xs font-medium">
            {item.name}
          </TooltipContent>
        </Tooltip>
      );
    }
    return inner;
  };

  const GroupDivider = ({ label }: { label: string }) => {
    if (collapsed) return <div className="h-px bg-sidebar-border mx-2.5 my-2" />;
    return (
      <div className="mx-3 mt-4 mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-sidebar-muted">
            {label}
          </span>
          <div className="flex-1 h-px bg-sidebar-border" />
        </div>
      </div>
    );
  };

  return (
    <aside
      className={`bg-sidebar border-r border-sidebar-border transition-[width] duration-200 ease-out flex flex-col shrink-0 ${
        collapsed ? 'w-[48px]' : 'w-[220px]'
      }`}
    >
      {/* Logo / Brand */}
      <div
        className={`h-[var(--topbar-height)] flex items-center border-b border-sidebar-border shrink-0 ${
          collapsed ? 'justify-center' : 'px-3 gap-2.5'
        }`}
      >
        <div className="flex items-center justify-center w-7 h-7 rounded-[3px] bg-primary shrink-0">
          <Zap className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-semibold text-sidebar-foreground leading-none tracking-tight truncate">
              PI Platform
            </p>
            <p className="text-[10px] text-sidebar-muted leading-none mt-0.5 truncate">
              ABCDH Technologies
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2 overflow-y-auto scrollbar-none" aria-label="Navegación principal">
        <div className="space-y-0.5">
          {mainItems.map((item) => (
            <NavLink key={item.path} item={item} />
          ))}
        </div>

        {analyticsItems.length > 0 && (
          <>
            <GroupDivider label="Análisis" />
            <div className="space-y-0.5">
              {analyticsItems.map((item) => (
                <NavLink key={item.path} item={item} />
              ))}
            </div>
          </>
        )}

        {adminItems.length > 0 && (
          <>
            <GroupDivider label="Administración" />
            <div className="space-y-0.5">
              {adminItems.map((item) => (
                <NavLink key={item.path} item={item} />
              ))}
            </div>
          </>
        )}

        <GroupDivider label="Usuario" />
        <div className="space-y-0.5">
          {userItems.map((item) => (
            <NavLink key={item.path} item={item} />
          ))}
        </div>
      </nav>

      {/* User info + collapse toggle */}
      <div className="border-t border-sidebar-border shrink-0">
        {user && !collapsed && (
          <div className="px-3 py-2.5 flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-full bg-primary/90 flex items-center justify-center shrink-0">
              <span className="text-[11px] font-semibold text-white">
                {user.name.charAt(0).toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-medium text-sidebar-foreground truncate">{user.name}</p>
              <p className="text-[10px] text-sidebar-muted capitalize truncate">
                {user.role.replace('_', ' ')}
              </p>
            </div>
          </div>
        )}
        {user && collapsed && (
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex justify-center py-2.5">
                <div className="w-7 h-7 rounded-full bg-primary/90 flex items-center justify-center cursor-default">
                  <span className="text-[11px] font-semibold text-white">
                    {user.name.charAt(0).toUpperCase()}
                  </span>
                </div>
              </div>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8} className="text-xs">
              {user.name}
            </TooltipContent>
          </Tooltip>
        )}

        {/* Collapse toggle */}
        <div className={`flex ${collapsed ? 'justify-center' : 'justify-end px-2'} pb-2`}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggleCollapsed}
                aria-label={collapsed ? 'Expandir sidebar' : 'Colapsar sidebar'}
                className="p-1.5 rounded-[3px] hover:bg-sidebar-accent transition-colors text-sidebar-muted hover:text-sidebar-foreground"
              >
                {collapsed ? (
                  <ChevronRight className="w-3.5 h-3.5" />
                ) : (
                  <ChevronLeft className="w-3.5 h-3.5" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8} className="text-xs">
              {collapsed ? 'Expandir' : 'Colapsar'}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </aside>
  );
}
