import { RouterProvider } from 'react-router';
import { router } from './routes.tsx';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Toaster } from 'sonner';

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <RouterProvider router={router} />
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
