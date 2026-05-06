import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useApiProjects } from '../hooks/useProjectData';
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandShortcut,
} from './ui/command';
import {
  LayoutGrid,
  Briefcase,
  ListChecks,
  CircleUser,
  SlidersHorizontal,
  Moon,
  Sun,
  LogOut,
  Search,
  ArrowRight,
} from 'lucide-react';

interface NavCommand {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  roles?: string[];
  keywords?: string;
}

const navCommands: NavCommand[] = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutGrid, keywords: 'inicio home overview resumen' },
  { name: 'Proyectos', path: '/projects', icon: Briefcase, keywords: 'projects lista list' },
  { name: 'Backlog', path: '/backlog', icon: ListChecks, keywords: 'tareas tasks kanban board' },
  { name: 'Mi Perfil', path: '/profile', icon: CircleUser, keywords: 'perfil profile usuario user' },
  { name: 'Configuración', path: '/settings', icon: SlidersHorizontal, keywords: 'settings ajustes preferences' },
];


export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { data: allProjects } = useApiProjects();

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      setOpen((prev) => !prev);
    }
  }, []);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const runCommand = useCallback((command: () => void) => {
    setOpen(false);
    command();
  }, []);

  const filteredNav = navCommands.filter((item) => {
    if (!item.roles) return true;
    return user && item.roles.includes(user.role);
  });

  return (
    <>
      {open && (
        <CommandDialog open={open} onOpenChange={setOpen} title="Command Palette" description="Busca páginas, proyectos o acciones">
      <CommandInput placeholder="Escribe un comando o busca..." />
      <CommandList>
        <CommandEmpty>
          <div className="flex flex-col items-center gap-2 py-4">
            <Search className="w-8 h-8 text-muted-foreground/40" />
            <p className="text-muted-foreground text-sm">Sin resultados</p>
          </div>
        </CommandEmpty>

        {/* Navigation */}
        <CommandGroup heading="Navegación">
          {filteredNav.map((item) => {
            const Icon = item.icon;
            return (
              <CommandItem
                key={item.path}
                value={`${item.name} ${item.keywords || ''}`}
                onSelect={() => runCommand(() => navigate(item.path))}
              >
                <Icon className="w-4 h-4 text-muted-foreground" />
                <span>{item.name}</span>
                <ArrowRight className="ml-auto w-3 h-3 text-muted-foreground/50" />
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        {/* Projects quick access — dynamic from API */}
        {allProjects && allProjects.length > 0 && (
          <CommandGroup heading="Proyectos">
            {allProjects.map((project) => (
              <CommandItem
                key={project.id_project}
                value={`proyecto ${project.name}`}
                onSelect={() => runCommand(() => navigate(`/projects/${project.id_project}`))}
              >
                <Briefcase className="w-4 h-4 text-muted-foreground" />
                <span>{project.name}</span>
                <ArrowRight className="ml-auto w-3 h-3 text-muted-foreground/50" />
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandSeparator />

        {/* Actions */}
        <CommandGroup heading="Acciones">
          <CommandItem
            value="cambiar tema dark light oscuro claro"
            onSelect={() => runCommand(toggleTheme)}
          >
            {theme === 'dark' ? (
              <Sun className="w-4 h-4 text-muted-foreground" />
            ) : (
              <Moon className="w-4 h-4 text-muted-foreground" />
            )}
            <span>{theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}</span>
            <CommandShortcut>⌘T</CommandShortcut>
          </CommandItem>
          <CommandItem
            value="cerrar sesion logout salir"
            onSelect={() => runCommand(() => { logout(); navigate('/login'); })}
          >
            <LogOut className="w-4 h-4 text-muted-foreground" />
            <span>Cerrar sesión</span>
            <CommandShortcut>⌘Q</CommandShortcut>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
      )}
    </>
  );
}
