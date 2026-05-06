import { Navigate, Outlet } from 'react-router';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette } from './CommandPalette';
import { PageTransition } from './PageTransition';
import { ScrollToTop } from './ScrollToTop';
import { ErrorBoundary } from './ErrorBoundary';
import { useGlobalShortcuts } from '../hooks/useGlobalShortcuts';
import { useAuth } from '../context/AuthContext';

export function AppLayout() {
  const { loading, isAuthenticated } = useAuth();
  useGlobalShortcuts();

  if (loading) {
    return <div className="h-screen bg-background" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <ScrollToTop />
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Topbar />
        <div className="flex-1 flex overflow-hidden">
          <main className="flex-1 overflow-y-auto min-w-0 scrollbar-app">
            <ErrorBoundary>
              <PageTransition>
                <Outlet />
              </PageTransition>
            </ErrorBoundary>
          </main>
        </div>
      </div>
      <CommandPalette />
    </div>
  );
}
