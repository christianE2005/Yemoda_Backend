import { Link, useLocation } from 'react-router';
import { ArrowLeft, Home, MapPinOff } from 'lucide-react';
import { motion } from 'motion/react';

export default function NotFound() {
  const location = useLocation();

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mx-auto mb-6"
        >
          <MapPinOff className="w-7 h-7 text-muted-foreground" />
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="text-6xl font-bold text-foreground mb-2 tabular-nums"
        >
          404
        </motion.h1>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <h2 className="text-lg font-semibold text-foreground mb-2">Página no encontrada</h2>
          <p className="text-sm text-muted-foreground mb-1">
            La ruta <code className="px-1.5 py-0.5 bg-muted rounded text-xs font-mono">{location.pathname}</code> no existe.
          </p>
          <p className="text-sm text-muted-foreground mb-8">
            Verifica la URL o regresa a una sección disponible.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          className="flex items-center justify-center gap-3"
        >
          <Link
            to="/dashboard"
            className="px-4 py-2 bg-primary hover:bg-primary-hover text-primary-foreground rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors"
          >
            <Home className="w-4 h-4" />
            Ir al Dashboard
          </Link>
          <button
            onClick={() => window.history.back()}
            className="px-4 py-2 bg-secondary hover:bg-accent text-foreground rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Volver atrás
          </button>
        </motion.div>
      </div>
    </div>
  );
}
