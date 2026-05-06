import { type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  children: ReactNode;
}

export function LoadingButton({ loading, children, disabled, className = '', ...props }: LoadingButtonProps) {
  return (
    <button
      disabled={loading || disabled}
      className={`${className} ${loading ? 'opacity-80 cursor-not-allowed' : ''}`}
      {...props}
    >
      {loading ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span>Cargando...</span>
        </>
      ) : (
        children
      )}
    </button>
  );
}
