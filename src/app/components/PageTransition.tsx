import { motion } from 'motion/react';
import { useLocation } from 'react-router';
import { ReactNode } from 'react';

export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();

  return (
    <motion.div
      key={location.pathname}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      className="h-full"
    >
      {children}
    </motion.div>
  );
}
