import { useMemo } from 'react';

interface CodeDiffViewerProps {
  patch: string;
  filename: string;
}

interface DiffLine {
  type: 'add' | 'remove' | 'context' | 'header';
  content: string;
  oldLine?: number;
  newLine?: number;
}

function parsePatch(patch: string): DiffLine[] {
  const lines = patch.split('\n');
  const result: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const line of lines) {
    if (line.startsWith('@@')) {
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldLine = parseInt(match[1], 10);
        newLine = parseInt(match[2], 10);
      }
      result.push({ type: 'header', content: line });
    } else if (line.startsWith('+')) {
      result.push({ type: 'add', content: line.slice(1), newLine: newLine++ });
    } else if (line.startsWith('-')) {
      result.push({ type: 'remove', content: line.slice(1), oldLine: oldLine++ });
    } else {
      result.push({ type: 'context', content: line.startsWith(' ') ? line.slice(1) : line, oldLine: oldLine++, newLine: newLine++ });
    }
  }
  return result;
}

const lineStyles: Record<DiffLine['type'], string> = {
  add: 'bg-emerald-500/10 text-emerald-400',
  remove: 'bg-red-500/10 text-red-400',
  context: 'text-muted-foreground',
  header: 'bg-primary/5 text-primary font-medium',
};

const gutterStyles: Record<DiffLine['type'], string> = {
  add: 'bg-emerald-500/5 text-emerald-500/50',
  remove: 'bg-red-500/5 text-red-500/50',
  context: 'text-muted-foreground/40',
  header: 'bg-primary/5 text-primary/40',
};

export function CodeDiffViewer({ patch, filename }: CodeDiffViewerProps) {
  const parsedLines = useMemo(() => parsePatch(patch), [patch]);

  const ext = filename.split('.').pop() ?? '';
  const isCode = ['ts', 'tsx', 'js', 'jsx', 'py', 'css', 'html', 'json', 'yml', 'yaml', 'md'].includes(ext);

  return (
    <div className="rounded-[4px] border border-border overflow-hidden text-[11px] leading-[18px]">
      {/* File header */}
      <div className="px-3 py-1.5 bg-surface-secondary/50 border-b border-border flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full shrink-0 ${isCode ? 'bg-primary' : 'bg-muted-foreground/40'}`} />
        <span className="font-mono text-[10px] text-foreground truncate">{filename}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full font-mono">
          <tbody>
            {parsedLines.map((line, i) => (
              <tr key={i} className={`${lineStyles[line.type]} hover:brightness-110 transition-all`}>
                {/* Old line number */}
                <td className={`w-10 text-right px-1.5 select-none text-[10px] border-r border-border/30 ${gutterStyles[line.type]}`}>
                  {line.type === 'header' ? '' : line.oldLine ?? ''}
                </td>
                {/* New line number */}
                <td className={`w-10 text-right px-1.5 select-none text-[10px] border-r border-border/30 ${gutterStyles[line.type]}`}>
                  {line.type === 'header' ? '' : line.newLine ?? ''}
                </td>
                {/* Marker */}
                <td className="w-4 text-center select-none">
                  {line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ''}
                </td>
                {/* Content */}
                <td className="px-2 whitespace-pre">{line.content}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
