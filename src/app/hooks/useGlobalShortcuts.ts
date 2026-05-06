import { useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router';

const gotoShortcuts: Record<string, string> = {
  d: '/dashboard',
  p: '/projects',
  b: '/backlog',
  a: '/alerts',
  r: '/reports',
  s: '/settings',
};

export function useGlobalShortcuts() {
  const navigate = useNavigate();
  const gPendingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    const tag = target.tagName.toLowerCase();
    // Don't trigger in inputs, textareas, selects, or contenteditable
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) return;
    // Don't trigger with modifier keys (Ctrl+K is handled by CommandPalette)
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    // "/" → open command palette (focus search)
    if (e.key === '/') {
      e.preventDefault();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
      return;
    }

    // "g" → start goto sequence
    if (e.key === 'g' && !gPendingRef.current) {
      gPendingRef.current = true;
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        gPendingRef.current = false;
      }, 800);
      return;
    }

    // Second key after "g"
    if (gPendingRef.current) {
      gPendingRef.current = false;
      clearTimeout(timerRef.current);
      const path = gotoShortcuts[e.key];
      if (path) {
        e.preventDefault();
        navigate(path);
      }
    }
  }, [navigate]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timerRef.current);
    };
  }, [handleKeyDown]);
}
