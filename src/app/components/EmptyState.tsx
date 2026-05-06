import { Search, Inbox, FileX } from 'lucide-react';
import { motion } from 'motion/react';

interface EmptyStateProps {
  icon?: 'search' | 'inbox' | 'file';
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

const icons = {
  search: Search,
  inbox: Inbox,
  file: FileX,
};

function FloatingDots() {
  return (
    <svg width="120" height="32" viewBox="0 0 120 32" fill="none" className="mx-auto mb-3 text-muted-foreground/20">
      <motion.circle cx="20" cy="16" r="4" fill="currentColor"
        animate={{ y: [0, -6, 0] }} transition={{ duration: 1.8, repeat: Infinity, delay: 0 }} />
      <motion.circle cx="44" cy="16" r="3" fill="currentColor"
        animate={{ y: [0, -8, 0] }} transition={{ duration: 1.8, repeat: Infinity, delay: 0.2 }} />
      <motion.circle cx="64" cy="16" r="5" fill="currentColor"
        animate={{ y: [0, -5, 0] }} transition={{ duration: 1.8, repeat: Infinity, delay: 0.4 }} />
      <motion.circle cx="86" cy="16" r="3" fill="currentColor"
        animate={{ y: [0, -7, 0] }} transition={{ duration: 1.8, repeat: Infinity, delay: 0.6 }} />
      <motion.circle cx="106" cy="16" r="4" fill="currentColor"
        animate={{ y: [0, -6, 0] }} transition={{ duration: 1.8, repeat: Infinity, delay: 0.8 }} />
    </svg>
  );
}

export function EmptyState({ icon = 'inbox', title, description, action }: EmptyStateProps) {
  const Icon = icons[icon];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="flex flex-col items-center justify-center py-16 px-6"
    >
      <FloatingDots />
      <motion.div
        initial={{ scale: 0.8 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.35, delay: 0.1, ease: 'easeOut' }}
        className="w-14 h-14 rounded-full bg-gradient-to-br from-muted to-muted/50 flex items-center justify-center mb-4 shadow-sm"
      >
        <Icon className="w-6 h-6 text-muted-foreground" />
      </motion.div>
      <h3 className="text-sm font-semibold text-foreground mb-1">{title}</h3>
      {description && (
        <p className="text-xs text-muted-foreground text-center max-w-xs leading-relaxed">{description}</p>
      )}
      {action && (
        <motion.button
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          onClick={action.onClick}
          className="mt-5 px-4 py-2 text-xs font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-md transition-colors shadow-sm"
        >
          {action.label}
        </motion.button>
      )}
    </motion.div>
  );
}
